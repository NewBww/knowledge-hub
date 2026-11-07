"""External-agent queue, not a built-in AI/provider harness."""
import pytest
from knowledge_hub.core import DomainError
from knowledge_hub.store import Store
from knowledge_hub.intake import Intake
from knowledge_hub.intake_models import CaptureInput


def test_human_enabled_agent_queue_is_bounded_and_local(tmp_path):
    from knowledge_hub.curator import Curator
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    capture = Intake(store).create(project, CaptureInput(text='secret synthetic paste', intent='Organize', files=[{'name': 'folder/note.txt', 'media_type': 'text/plain', 'content_base64': 'c291cmNlIHRleHQ='}]))
    curator = Curator(store)
    assert capture['status'] == 'pending_agent'
    with pytest.raises(DomainError, match='agent_access_disabled'):
        curator.capture_list(project)
    curator.set_agent_access(project, True)
    queue = Curator(store).capture_list(project, limit=1)
    assert queue['total'] == 1 and queue['next_offset'] is None
    assert 'text' not in queue['captures'][0] and 'intent' not in queue['captures'][0]
    view = curator.capture_get(project, capture['id'], max_chars=6)
    assert view['text'] == 'secret' and view['next_offset'] == 6
    assert 'text' not in view['files'][0]
    file_id = capture['files'][0]['id']
    source = curator.capture_get(project, capture['id'], source_id=file_id, max_chars=6)
    assert source['text'] == 'source'
    attachment = curator.capture_get(project, capture['id'], attachment_id=file_id, max_bytes=3)
    assert attachment['attachment']['content_base64'] == 'c291'
    assert attachment['attachment']['next_byte_offset'] == 3
    curator.set_agent_access(project, False)
    with pytest.raises(DomainError, match='agent_access_disabled'):
        curator.capture_get(project, capture['id'])


def test_claim_has_exclusive_persisted_snapshot_and_revision_lease(tmp_path):
    from knowledge_hub.curator import Curator
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    capture = Intake(store).create(project, CaptureInput(text='claim this source'))
    curator = Curator(store)
    curator.set_agent_access(project, True)
    with pytest.raises(DomainError, match='capture_snapshot_mismatch'):
        curator.claim(project, capture['id'], 'agent', '0' * 64, 0)
    with pytest.raises(DomainError, match='stale_revision'):
        curator.claim(project, capture['id'], 'agent', capture['snapshot_sha256'], 1)
    lease = curator.claim(project, capture['id'], 'agent', capture['snapshot_sha256'], 0)
    assert lease['base_revision'] == 0 and lease['claim_token']
    with pytest.raises(DomainError, match='capture_claimed'):
        Curator(store).claim(project, capture['id'], 'other agent', capture['snapshot_sha256'], 0)
    inspection = curator.capture_get(project, capture['id'])
    assert 'claim_token' not in inspection['claim']
    assert Intake(store).get(project, capture['id'])['claim']['claim_token'] == lease['claim_token']


def test_agent_submission_creates_only_pending_proposal_and_persists_suggestions(tmp_path, monkeypatch):
    import socket
    from knowledge_hub.curator import Curator, CurationSubmission
    def forbidden(*args, **kwargs):
        pytest.fail('Queue curation must never execute a provider request')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    capture = Intake(store).create(project, CaptureInput(text='Synthetic source fact'))
    curator = Curator(store)
    curator.set_agent_access(project, True)
    claim = curator.claim(project, capture['id'], 'my own harness', capture['snapshot_sha256'], 0)
    submission = CurationSubmission.model_validate({'snapshot_sha256': capture['snapshot_sha256'], 'claim_token': claim['claim_token'], 'base_revision': 0,
        'summary': 'Externally curated finding', 'operations': [{'op': 'upsert', 'title': 'Synthetic fact', 'body': 'Source-backed truth', 'kind': 'fact', 'evidence': [{'kind': 'document', 'locator': 'synthetic://source', 'label': 'Supplied source'}]}],
        'library_suggestions': [{'book_title': 'Guide', 'page_title': 'Topic', 'body': 'Suggested page'}]})
    result = curator.curation_submit(project, capture['id'], submission)
    assert result['warehouse_change']['status'] == 'pending'
    evidence = result['warehouse_change']['operations'][0]['evidence']
    assert evidence[0]['locator'] == 'synthetic://source'
    assert evidence[1]['locator'].startswith('capture:' + capture['id'])
    assert not store.knowledge(project)['items']
    saved = Intake(store).get(project, capture['id'])
    assert saved['status'] == 'proposed' and saved['result'] == result
    assert result['library_suggestions'][0]['page_title'] == 'Topic'
    assert Curator(store).curation_submit(project, capture['id'], submission) == result
    changed = submission.model_copy(update={'summary': 'different repeat'})
    with pytest.raises(DomainError, match='idempotency_conflict'):
        curator.curation_submit(project, capture['id'], changed)


def submission_for(capture, token, **changes):
    from knowledge_hub.curator import CurationSubmission
    data = {'snapshot_sha256': capture['snapshot_sha256'], 'claim_token': token, 'base_revision': 0,
            'summary': 'Synthetic draft', 'operations': [{'op': 'upsert', 'title': 'Fact', 'body': 'Text', 'kind': 'fact'}]}
    data.update(changes)
    return CurationSubmission.model_validate(data)


def test_duplicate_operations_are_a_sanitized_domain_error(tmp_path):
    from knowledge_hub.curator import Curator
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    capture = Intake(store).create(project, CaptureInput(text='source'))
    curator = Curator(store)
    curator.set_agent_access(project, True)
    claim = curator.claim(project, capture['id'], 'agent', capture['snapshot_sha256'], 0)
    operation = {'op': 'upsert', 'id': '00000000-0000-4000-8000-000000000001', 'title': 'Duplicate', 'body': 'Do not reflect this source in exceptions', 'kind': 'fact'}
    with pytest.raises(DomainError, match='invalid_curation_submission'):
        curator.curation_submit(project, capture['id'], submission_for(capture, claim['claim_token'], operations=[operation, operation]))


def test_concurrent_claims_have_exactly_one_winner(tmp_path):
    # Supplementary concurrency characterization of the claim boundary.
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from knowledge_hub.curator import Curator
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    capture = Intake(store).create(project, CaptureInput(text='one work item'))
    Curator(store).set_agent_access(project, True)
    barrier = Barrier(2)
    def claim(name):
        curator = Curator(store)
        barrier.wait(timeout=5)
        try:
            return curator.claim(project, capture['id'], name, capture['snapshot_sha256'], 0)
        except DomainError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ['agent-a', 'agent-b']))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert results.count('capture_claimed') == 1


def test_expired_claim_and_changed_revision_block_submission(tmp_path):
    from datetime import datetime, timedelta, timezone
    from knowledge_hub.curator import Curator
    from knowledge_hub.core import Proposal
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    intake = Intake(store)
    capture = intake.create(project, CaptureInput(text='source'))
    curator = Curator(store)
    curator.set_agent_access(project, True)
    lease = curator.claim(project, capture['id'], 'agent', capture['snapshot_sha256'], 0)
    saved = intake.get(project, capture['id'])
    saved['claim']['expires_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    intake.save(saved)
    with pytest.raises(DomainError, match='invalid_or_expired_claim'):
        curator.curation_submit(project, capture['id'], submission_for(capture, lease['claim_token']))
    replacement = curator.claim(project, capture['id'], 'replacement', capture['snapshot_sha256'], 0)
    assert replacement['claim_token'] != lease['claim_token']
    independent = store.propose(project, Proposal.model_validate({'base_revision': 0, 'idempotency_key': 'independent', 'summary': 'Human accepted another change', 'operations': [{'op': 'upsert', 'title': 'Independent', 'body': 'Accepted by human fixture', 'kind': 'fact'}]}))
    store.approve(project, independent['id'])
    with pytest.raises(DomainError, match='stale_revision'):
        curator.curation_submit(project, capture['id'], submission_for(capture, replacement['claim_token']))
    assert intake.get(project, capture['id'])['status'] == 'pending_agent'
    assert len(store.changes(project)) == 1


@pytest.mark.parametrize('kwargs', [{'max_chars': 20001}, {'offset': -1}, {'max_bytes': 1048577}, {'max_chars': True}])
def test_agent_capture_retrieval_limits_are_enforced(tmp_path, kwargs):
    from knowledge_hub.curator import Curator
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    capture = Intake(store).create(project, CaptureInput(text='source'))
    curator = Curator(store)
    curator.set_agent_access(project, True)
    with pytest.raises(DomainError, match='invalid_retrieval_limit'):
        curator.capture_get(project, capture['id'], **kwargs)
