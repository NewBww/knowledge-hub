"""Real SDK stdio contracts: local services, bounded reads, pending writes only."""
import base64
from contextlib import contextmanager
import json
import select
import subprocess
import sys

from knowledge_hub.curator import Curator
from knowledge_hub.intake import Intake
from knowledge_hub.intake_models import CaptureInput
from knowledge_hub.store import Store
from knowledge_hub.shared import SharedWarehouse


@contextmanager
def wire(path):
    process = subprocess.Popen(
        [sys.executable, '-m', 'knowledge_hub.cli', 'mcp', '--data-dir', str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8')
    assert process.stdin is not None and process.stdout is not None
    counter = 0

    def send(message):
        process.stdin.write(json.dumps(message) + '\n')
        process.stdin.flush()

    def rpc(method, params):
        nonlocal counter
        counter += 1
        send({'jsonrpc': '2.0', 'id': counter, 'method': method, 'params': params})
        while True:
            assert select.select([process.stdout], [], [], 20)[0], 'stdio response timed out'
            line = process.stdout.readline()
            assert line, 'stdio exited unexpectedly'
            response = json.loads(line)
            if response.get('id') == counter:
                assert 'error' not in response, response
                return response['result'], len(line.rstrip('\n'))

    try:
        rpc('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                           'clientInfo': {'name': 'synthetic-test', 'version': '1'}})
        send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        yield rpc
    finally:
        process.terminate()
        process.communicate(timeout=10)


def call(rpc, name, arguments, text_only=False):
    result, size = rpc('tools/call', {'name': name, 'arguments': arguments})
    assert not result.get('isError'), result
    if text_only:
        assert 'structuredContent' not in result
        assert len(result['content']) == 1 and result['content'][0]['type'] == 'text'
    return result.get('structuredContent') or json.loads(result['content'][0]['text']), size


def seed_capture(path):
    store = Store(path)
    project = SharedWarehouse(store).scope()
    capture = Intake(store).create(project, CaptureInput.model_validate({
        'text': 'synthetic source ' * 3000,
        'files': [{'name': 'synthetic.bin', 'media_type': 'application/octet-stream',
                   'content_base64': base64.b64encode(b'x' * 100000).decode()}]}))
    return store, project, capture


def test_capture_reads_require_human_access_and_are_explicit_bounded_text(tmp_path):
    store, project, capture = seed_capture(tmp_path)
    with wire(tmp_path) as rpc:
        denied, _ = rpc('tools/call', {'name': 'capture_list', 'arguments': {'project_id': project}})
        assert denied['isError'] and denied['content'][0]['text'] == 'agent_access_disabled'
        Curator(store).set_agent_access(project, True)
        listing, size = call(rpc, 'capture_list', {'project_id': project}, text_only=True)
        assert listing['total'] == 1 and listing['next_offset'] is None
        assert 'text' not in listing['captures'][0] and 'intent' not in listing['captures'][0]
        assert size < 10000
        detail, size = call(rpc, 'capture_get', {'capture_id': capture['id']}, text_only=True)
        assert len(detail['text']) == 4000 and detail['next_offset'] == 4000
        assert 'attachment' not in detail and size < 15000
        attachment, size = call(rpc, 'capture_get', {'capture_id': capture['id'],
            'attachment_id': capture['files'][0]['id']}, text_only=True)
        assert base64.b64decode(attachment['attachment']['content_base64']) == b'x' * 16384
        assert attachment['attachment']['next_byte_offset'] == 16384
        assert 'text' not in attachment and size < 30000
        Curator(store).set_agent_access(project, False)
        denied, _ = rpc('tools/call', {'name': 'capture_get', 'arguments': {'capture_id': capture['id']}})
        assert denied['isError'] and denied['content'][0]['text'] == 'agent_access_disabled'


def test_stdio_claim_submission_only_creates_pending_proposal(tmp_path):
    store, project, capture = seed_capture(tmp_path)
    Curator(store).set_agent_access(project, True)
    with wire(tmp_path) as rpc:
        lease, _ = call(rpc, 'capture_claim', {'capture_id': capture['id'],
            'claimant': 'Synthetic harness', 'snapshot_sha256': capture['snapshot_sha256'], 'base_revision': 0})
        submission = {'snapshot_sha256': capture['snapshot_sha256'], 'claim_token': lease['claim_token'],
            'base_revision': 0, 'summary': 'Synthetic curation',
            'operations': [{'op': 'upsert', 'title': 'Synthetic fact', 'body': 'Synthetic supported assertion', 'kind': 'fact'}],
            'library_suggestions': [{'book_title': 'Guide', 'page_title': 'Topic', 'body': 'Suggested reading'}]}
        args = {'capture_id': capture['id'], 'submission': submission}
        bad, _ = rpc('tools/call', {'name': 'curation_submit', 'arguments': {**args,
            'submission': {**submission, 'approved': True}}})
        assert bad['isError'] and bad['content'][0]['text'] == 'invalid_arguments'
        result, _ = call(rpc, 'curation_submit', args, text_only=True)
        assert result['warehouse_change']['status'] == 'pending'
        assert result['library_suggestions'] == submission['library_suggestions']
        assert call(rpc, 'curation_submit', args, text_only=True)[0] == result
        assert store.projects()[0]['revision'] == 0
        assert Intake(store).get(project, capture['id'])['status'] == 'proposed'
        with store.connect() as db:
            assert db.execute('SELECT count(*) FROM items').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM changes').fetchone()[0] == 1
        # Direct already-curated proposals do not require a capture or access permission.
        Curator(store).set_agent_access(project, False)
        direct, _ = call(rpc, 'change_propose', {'proposal': {
            'base_revision': 0, 'idempotency_key': 'direct', 'summary': 'No capture needed',
            'operations': [{'op': 'upsert', 'title': 'Direct', 'body': 'Synthetic', 'kind': 'fact'}]}})
        assert direct['status'] == 'pending'
        assert store.projects()[0]['revision'] == 0


def test_library_proposal_pending_then_bounded_reader_projections(tmp_path):
    from uuid import uuid4
    from knowledge_hub.library import Library
    store = Store(tmp_path)
    project = SharedWarehouse(store).scope()
    pages = [str(uuid4()) for _ in range(3)]
    books = [str(uuid4()) for _ in range(3)]
    body = ('🧪\x00Synthetic "reading"\\ ' * 5000)
    body = body[:100000]
    operations = [{'op': 'upsert_page', 'id': page, 'base_revision': 0,
        'title': f'Page {i}', 'state': 'published', 'sections': [{'id': str(uuid4()),
        'kind': 'editorial', 'body': body}]} for i, page in enumerate(pages)]
    operations += [{'op': 'upsert_book', 'id': book, 'base_revision': 0, 'title': f'Book {i}',
        'overview': 'O' * 10000, 'purpose': 'P' * 4000, 'state': 'published', 'page_ids': pages}
        for i, book in enumerate(books)]
    proposal = {'base_revision': 0, 'idempotency_key': 'library-mcp', 'summary': 'Synthetic reader', 'operations': operations}
    with wire(tmp_path) as rpc:
        result, _ = call(rpc, 'library_propose', {'proposal': proposal}, text_only=True)
        assert result['status'] == 'pending' and store.projects()[0]['revision'] == 0
        assert Library(store).books(project) == []
        assert call(rpc, 'library_propose', {'proposal': proposal}, text_only=True)[0] == result
        # Trusted fixture approval only. Actual human-session HTTP review is parent-owned.
        Library(store).approve(project, result['id'])
        listing, size = call(rpc, 'library_list', {'limit': 2}, text_only=True)
        assert listing['total'] == 3 and listing['next_offset'] == 2 and len(listing['books']) == 2
        assert size < 3000
        assert not {'overview', 'purpose', 'page_ids', 'pages'}.intersection(listing['books'][0])
        detail, size = call(rpc, 'library_get', {'book_id': books[0], 'limit': 2}, text_only=True)
        assert [page['id'] for page in detail['pages']] == pages[:2]
        assert detail['next_offset'] == 2 and detail['page_count'] == 3 and size < 4000
        assert 'sections' not in detail['pages'][0]
        tail, _ = call(rpc, 'library_get', {'book_id': books[0], 'offset': 2}, text_only=True)
        assert [page['id'] for page in tail['pages']] == pages[2:] and tail['next_offset'] is None
        fragment, size = call(rpc, 'library_page_get', {'page_id': pages[0]}, text_only=True)
        assert fragment['section']['body'] == body[:4000] and fragment['next_body_offset'] == 4000
        assert fragment['section_count'] == 1 and fragment['revision'] == 1 and size < 12000
        fragment2, _ = call(rpc, 'library_page_get', {'page_id': pages[0],
            'body_offset': 4000, 'max_chars': 100, 'expected_revision': 1}, text_only=True)
        assert fragment2['section']['body'] == body[4000:4100]
        stale, _ = rpc('tools/call', {'name': 'library_page_get', 'arguments': {
            'page_id': pages[0], 'expected_revision': 0}})
        assert stale['isError'] and stale['content'][0]['text'] == 'stale_revision'
