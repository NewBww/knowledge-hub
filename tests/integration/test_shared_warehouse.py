"""Shared namespace acceptance using synthetic stores only."""
from knowledge_hub.store import Store
import json
import subprocess
import sys
import pytest
from uuid import uuid4
from knowledge_hub.core import Proposal
from knowledge_hub.library import Library
from knowledge_hub.library_models import LibraryProposal
from knowledge_hub.intake import Intake
from knowledge_hub.intake_models import CaptureInput
from knowledge_hub.privacy import AgentAccess


def legacy_fixture(root):
    """Use the genuine v2 helpers, before opening the shared application."""
    store = Store(root)
    records = []
    for number in range(2):
        scope = store.create_project(f'Synthetic {number}', 'Synthetic provenance')['id']
        change = store.propose(scope, Proposal(base_revision=0, idempotency_key='same-key', summary='Synthetic fact', operations=[dict(op='upsert', title=f'Fact {number}', body='Evidence-backed synthetic fact', kind='fact', evidence=[dict(kind='document', locator=f'synthetic:{number}', label='Synthetic')])]))
        approved = store.approve(scope, change['id'])
        item = approved['operations'][0]['id']
        page, book, section = [str(uuid4()) for _ in range(3)]
        library = Library(store)
        publication = library.propose(scope, LibraryProposal(base_revision=1, idempotency_key='same-key', summary='Synthetic reader', operations=[
            dict(op='upsert_page', id=page, base_revision=0, title=f'Page {number}', state='published', sections=[dict(id=section, kind='factual', body='Synthetic reading', supports=[dict(item_id=item, revision=1)])]),
            dict(op='upsert_book', id=book, base_revision=0, title=f'Book {number}', state='published', page_ids=[page])]))
        library.approve(scope, publication['id'])
        pending = store.propose(scope, Proposal(base_revision=2, idempotency_key='pending', summary='Pending synthetic', operations=[dict(op='upsert', id=item, title=f'Updated {number}', body='Pending', kind='fact')]))
        rejected = store.propose(scope, Proposal(base_revision=2, idempotency_key='rejected', summary='Rejected synthetic', operations=[dict(op='upsert', title='Rejected', body='No', kind='question')]))
        store.reject(scope, rejected['id'])
        library_pending = library.propose(scope, LibraryProposal(base_revision=2, idempotency_key='pending', summary='Pending reader', operations=[dict(op='upsert_book', id=book, base_revision=1, title='Revised book', page_ids=[page])]))
        capture = Intake(store).create(scope, CaptureInput(text=f'Synthetic capture {number}'))
        AgentAccess(store).set(scope, True)
        records.append(dict(scope=scope, item=item, book=book, page=page, pending=pending, library_pending=library_pending, capture=capture,
                            history=store.changes(scope), library_history=library.changes(scope)))
    return store, records


def test_v2_scopes_merge_without_losing_evidence_history_or_permissions(tmp_path):
    from knowledge_hub.shared import SharedWarehouse
    store, records = legacy_fixture(tmp_path)
    shared = SharedWarehouse(store)
    scope = shared.scope()
    assert shared.state() == dict(revision=4, item_count=2, review_count=0, book_count=2,
                                 migration=dict(schema=3, status='complete', legacy_scope_count=2, agent_reconsent_required=True))
    assert {item['id'] for item in store.knowledge(scope)['items']} == {r['item'] for r in records}
    for record in records:
        item = store.get_item(scope, record['item'])
        assert item['evidence'][0]['locator'].startswith('synthetic:')
        assert Library(store).page(scope, record['page'])['support_state'] == 'current'
        assert Library(store).book(scope, record['book'])['page_ids'] == [record['page']]
        histories = {c['id']: c for c in store.changes(scope)}
        for original in record['history']:
            migrated = histories[original['id']]
            assert migrated['status'] == original['status']
            assert migrated['operations'] == original['operations']
            assert migrated['migration']['original_project_id'] == record['scope']
        assert histories[record['pending']['id']]['base_revision'] == 4
        capture = Intake(store).get(scope, record['capture']['id'])
        assert capture['text'] == record['capture']['text']
        assert capture['migration']['original_snapshot_sha256'] == record['capture']['snapshot_sha256']
        assert not AgentAccess(store).get(record['scope'])['agent_access']
    assert not AgentAccess(store).get(scope)['agent_access']
    assert len({r['id'] for r in store.changes(scope)}) == 6
    assert len(Library(store).changes(scope)) == 4
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM shared_legacy_rows').fetchone()[0] == 16
        assert db.execute('SELECT count(*) FROM shared_manifest_journal WHERE completed=0').fetchone()[0] == 0
    before = shared.state(), store.changes(scope), Intake(store).list(scope)
    assert (SharedWarehouse(Store(tmp_path)).state(), store.changes(scope), Intake(store).list(scope)) == before
    import sqlite3
    with sqlite3.connect(tmp_path / 'knowledge.sqlite3.v2.bak') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM projects').fetchone()[0] == 2



def test_shared_namespace_rejects_repartitioning(tmp_path):
    from knowledge_hub.shared import SharedWarehouse
    from knowledge_hub.core import DomainError
    store, records = legacy_fixture(tmp_path)
    shared = SharedWarehouse(store)
    with pytest.raises(DomainError, match='project_scope_removed'):
        store.create_project('A hidden partition')
    with pytest.raises(DomainError, match='project_scope_removed'):
        store.knowledge(records[0]['scope'])
    assert shared.knowledge()['total'] == 2
    item = shared.get_item(records[0]['item'])
    assert 'project_id' not in item
    assert len(shared.changes()) == 6


def test_shared_installation_has_stable_empty_scope(tmp_path):
    from knowledge_hub.shared import SharedWarehouse
    shared = SharedWarehouse(Store(tmp_path))
    scope = shared.scope()
    assert shared.state() == {
        'revision': 0, 'item_count': 0, 'review_count': 0, 'book_count': 0,
        'migration': {'schema': 3, 'status': 'complete', 'legacy_scope_count': 0,
                      'agent_reconsent_required': False},
    }
    assert SharedWarehouse(Store(tmp_path)).scope() == scope
    with shared.store.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3


def test_manifest_migration_recovers_after_real_process_death(tmp_path):
    store, records = legacy_fixture(tmp_path)
    code = """
import os, sys
from knowledge_hub.store import Store
import knowledge_hub.shared as module
original = module.private_write
def interrupted(path, content):
    original(path, content)
    if path.name == 'capture.json':
        os._exit(73)
module.private_write = interrupted
module.SharedWarehouse(Store(sys.argv[1]))
"""
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 73, result.stderr
    with store.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert db.execute('SELECT count(*) FROM shared_manifest_journal WHERE completed=0').fetchone()[0] == 2
    recovery = """
import json, sys
from knowledge_hub.store import Store
from knowledge_hub.shared import SharedWarehouse
from knowledge_hub.intake import Intake
s=Store(sys.argv[1]); w=SharedWarehouse(s)
print(json.dumps({'state':w.state(), 'captures':Intake(s).list(w.scope())}))
"""
    recovered = subprocess.run([sys.executable, '-c', recovery, str(tmp_path)], capture_output=True, text=True)
    assert recovered.returncode == 0, recovered.stderr
    data = json.loads(recovered.stdout)
    assert data['state']['migration']['status'] == 'complete'
    assert {c['id'] for c in data['captures']} == {r['capture']['id'] for r in records}
    from knowledge_hub.shared import SharedWarehouse
    scope = SharedWarehouse(Store(tmp_path)).scope()
    assert not AgentAccess(store).get(scope)['agent_access']
    assert len(store.changes(scope)) == 6


def test_bad_manifest_rolls_back_canonical_merge_and_denies_access(tmp_path):
    from knowledge_hub.shared import SharedWarehouse
    from knowledge_hub.core import DomainError
    store, records = legacy_fixture(tmp_path)
    manifest = tmp_path / 'captures' / records[0]['capture']['id'] / 'capture.json'
    payload = json.loads(manifest.read_text())
    payload['text'] = 'Tampered synthetic source'
    manifest.write_text(json.dumps(payload))
    with pytest.raises(DomainError, match='capture_integrity_error'):
        SharedWarehouse(store)
    with store.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='shared_workspace'").fetchone()
    for r in records:
        assert store.get_item(r['scope'], r['item'])
        assert not AgentAccess(store).get(r['scope'])['agent_access']
    # Fix the synthetic corruption and retry: revocation must not erase the
    # original consent audit when the database transaction previously rolled back.
    manifest.write_text(json.dumps(records[0]['capture']))
    SharedWarehouse(Store(tmp_path))
    with store.connect() as db:
        archived = json.loads(db.execute("SELECT original FROM shared_legacy_settings WHERE name='capture-agent-access.json'").fetchone()[0])
    assert archived == {r['scope']: True for r in records}


def test_partial_curator_commit_does_not_become_duplicate_work(tmp_path):
    from knowledge_hub.shared import SharedWarehouse
    store, records = legacy_fixture(tmp_path)
    r = records[0]
    capture = r['capture']
    capture['claim'] = dict(claim_token=str(uuid4()), base_revision=2, expires_at='2099-01-01T00:00:00+00:00', claimant='synthetic')
    capture['submission_sha256'] = 'a' * 64
    Intake(store).save(capture)
    committed = store.propose(r['scope'], Proposal(base_revision=2, idempotency_key='capture:' + capture['id'], summary='Committed before process death', operations=[dict(op='upsert', title='Recovered pending work', body='Synthetic only', kind='fact')]))
    shared = SharedWarehouse(store)
    migrated = Intake(store).get(shared.scope(), capture['id'])
    assert migrated['status'] == 'proposed'
    assert migrated['result']['warehouse_change']['id'] == committed['id']
    assert 'claim' not in migrated
    assert migrated['migration']['original_submission_sha256'] == 'a' * 64


def test_concurrent_processes_open_exactly_one_shared_namespace(tmp_path):
    store, records = legacy_fixture(tmp_path)
    code = """
import json, sys
from knowledge_hub.store import Store
from knowledge_hub.shared import SharedWarehouse
w=SharedWarehouse(Store(sys.argv[1]))
print(json.dumps({'scope':w.scope(), 'state':w.state()}))
"""
    processes = [subprocess.Popen([sys.executable, '-c', code, str(tmp_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(3)]
    outputs = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        outputs.append(json.loads(stdout))
    assert len({out['scope'] for out in outputs}) == 1
    assert all(out['state']['item_count'] == 2 for out in outputs)
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM shared_workspace').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM shared_legacy_rows').fetchone()[0] == 16


def test_library_rejection_and_exact_original_rows_are_archived(tmp_path):
    from knowledge_hub.shared import SharedWarehouse
    store, records = legacy_fixture(tmp_path)
    record = records[0]
    library = Library(store)
    rejected = library.propose(record['scope'], LibraryProposal(base_revision=2, idempotency_key='rejected', summary='Synthetic rejected reader', operations=[dict(op='upsert_book', id=record['book'], base_revision=1, title='Rejected title', page_ids=[record['page']])]))
    library.reject(record['scope'], rejected['id'])
    before = {}
    with store.connect() as db:
        for table in ('items', 'changes', 'library_books', 'library_pages', 'library_changes'):
            for row in db.execute(f'SELECT * FROM {table}'):
                before[(table, row['id'])] = dict(row)
    shared = SharedWarehouse(store)
    with store.connect() as db:
        after = {(row['table_name'],row['id']):json.loads(row['original']) for row in db.execute('SELECT * FROM shared_legacy_rows')}
    assert after == before
    migrated = {c['id']:c for c in library.changes(shared.scope())}
    assert migrated[rejected['id']]['status'] == 'rejected'
    assert migrated[rejected['id']]['base_revision'] == 2
    pending = migrated[record['library_pending']['id']]
    assert pending['base_revision'] == 4
    library.approve(shared.scope(), pending['id'])
    assert library.book(shared.scope(), record['book'])['title'] == 'Revised book'


def test_future_schema_is_refused_without_writes(tmp_path):
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute('PRAGMA user_version=999')
    before = store.path.read_bytes()
    with pytest.raises(RuntimeError, match='newer_schema'):
        Store(tmp_path)
    assert store.path.read_bytes() == before
