from knowledge_hub.store import Store
from knowledge_hub.core import Proposal, DomainError
import pytest
from uuid import uuid4


def proposal(base=0, key='one', **operation):
    return Proposal(base_revision=base, idempotency_key=key, summary='Synthetic change', operations=[
        dict(op='upsert', title='Synthetic fact', body='First body', kind='fact', **operation)])


def test_proposal_is_preview_only_and_persists(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('Synthetic', '')
    change = store.propose(project['id'], proposal())
    assert change['status'] == 'pending'
    assert change['base_revision'] == 0
    assert len(change['impact']['affected_ids']) == 1
    assert store.knowledge(project['id']) == {'items': [], 'total': 0}
    assert Store(tmp_path).changes(project['id']) == [change]
    assert store.projects()[0]['revision'] == 0


def test_empty_store_projects_persist(tmp_path):
    store = Store(tmp_path)
    assert store.projects() == []
    p = store.create_project('Synthetic', 'Testing only')
    assert p['revision'] == 0
    assert p['item_count'] == 0
    assert Store(tmp_path).projects() == [p]


def test_approval_is_atomic_persistent_revision(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    change = store.propose(p, proposal(evidence=[{'kind': 'observation', 'locator': 'synthetic:test', 'label': 'Test'}]))
    applied = store.approve(p, change['id'])
    assert applied['status'] == 'approved'
    assert applied['result_revision'] == 1
    item = Store(tmp_path).knowledge(p)['items'][0]
    assert item['state'] == 'current'
    assert item['revision'] == 1
    assert item['id'] == change['operations'][0]['id']
    assert item['evidence'][0]['locator'] == 'synthetic:test'
    assert store.projects()[0]['item_count'] == 1
    assert store.approve(p, change['id']) == applied
    assert store.projects()[0]['revision'] == 1


def test_stale_approval_does_not_change_any_row(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    first = store.propose(p, proposal())
    stale = store.propose(p, proposal(key='stale'))
    store.approve(p, first['id'])
    before = store.knowledge(p), store.projects(), store.changes(p)
    with pytest.raises(DomainError, match='stale_revision'):
        store.approve(p, stale['id'])
    assert (store.knowledge(p), store.projects(), store.changes(p)) == before


def test_proposals_idempotent_but_key_cannot_change_payload(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    original = store.propose(p, proposal())
    assert store.propose(p, proposal()) == original
    altered = proposal().model_copy(update={'summary': 'Different'})
    with pytest.raises(DomainError, match='idempotency_conflict'):
        store.propose(p, altered)
    assert store.changes(p) == [original]


@pytest.mark.parametrize('bad_reference', ['foreign_item', 'missing_item', 'foreign_dependency', 'missing_dependency'])
def test_invalid_references_leave_database_unchanged(tmp_path, bad_reference):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    other = store.create_project('Other', '')['id']
    foreign = store.propose(other, proposal())
    store.approve(other, foreign['id'])
    foreign_id = foreign['operations'][0]['id']
    reference = foreign_id if bad_reference.startswith('foreign') else str(uuid4())
    field = 'depends_on' if bad_reference.endswith('dependency') else 'id'
    mutation = proposal(**{field: [reference] if field == 'depends_on' else reference})
    before = store.knowledge(p), store.projects(), store.changes(p), store.knowledge(other)
    with pytest.raises(DomainError, match='invalid_reference'):
        store.propose(p, mutation)
    assert (store.knowledge(p), store.projects(), store.changes(p), store.knowledge(other)) == before


def test_stale_proposal_rejected_without_pending_write(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    first = store.propose(p, proposal())
    store.approve(p, first['id'])
    with pytest.raises(DomainError, match='stale_revision'):
        store.propose(p, proposal(key='stale'))
    assert len(store.changes(p)) == 1


def test_rejection_prevents_later_approval(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    pending = store.propose(p, proposal())
    assert store.reject(p, pending['id'])['status'] == 'rejected'
    with pytest.raises(DomainError, match='not_pending'):
        store.approve(p, pending['id'])
    assert store.knowledge(p)['total'] == 0
    assert store.projects()[0]['revision'] == 0






