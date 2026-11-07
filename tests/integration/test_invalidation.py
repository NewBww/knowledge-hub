from knowledge_hub.store import Store
from knowledge_hub.core import Proposal


def change(store, project, revision, key, **operation):
    op = dict(op='upsert', title=key, body='Synthetic only', kind='fact')
    op.update(operation)
    return store.propose(project, Proposal(base_revision=revision, idempotency_key=key, summary=key, operations=[op]))


def add(store, project, revision, key, **operation):
    proposal = change(store, project, revision, key, **operation)
    store.approve(project, proposal['id'])
    return proposal['operations'][0]['id']


def test_transitive_invalidation_cycles_and_project_isolation(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    other = store.create_project('Other', '')['id']
    a = add(store, p, 0, 'a')
    b = add(store, p, 1, 'b', depends_on=[a])
    c = add(store, p, 2, 'c', depends_on=[b])
    unrelated = add(store, p, 3, 'unrelated')
    other_id = add(store, other, 0, 'other')
    correction = change(store, p, 4, 'correct-a', id=a)
    assert correction['impact'] == {'affected_ids': sorted([a, b, c]), 'review_required_ids': sorted([b, c])}
    store.approve(p, correction['id'])
    items = {item['id']: item for item in store.knowledge(p)['items']}
    assert items[a]['state'] == 'current'
    assert items[b]['state'] == items[c]['state'] == 'needs_review'
    assert items[unrelated]['state'] == 'current'
    assert store.knowledge(other)['items'][0]['id'] == other_id
    assert store.knowledge(other)['items'][0]['state'] == 'current'
    assert next(project for project in store.projects() if project['id'] == p)['review_count'] == 2


def test_invalid_support_cannot_be_silently_current(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    a = add(store, p, 0, 'a')
    b = add(store, p, 1, 'b', depends_on=[a])
    add(store, p, 2, 'correct-a', id=a)
    pending = change(store, p, 3, 'unsupported', depends_on=[b])
    assert pending['impact']['review_required_ids'] == [pending['operations'][0]['id']]
    store.approve(p, pending['id'])
    item = next(i for i in store.knowledge(p)['items'] if i['title'] == 'unsupported')
    assert item['state'] == 'needs_review'


def test_cycle_closure_terminates(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    a = add(store, p, 0, 'a')
    b = add(store, p, 1, 'b', depends_on=[a])
    add(store, p, 2, 'cycle', id=a, depends_on=[b])
    correction = change(store, p, 3, 'break-cycle', id=a)
    assert correction['impact']['affected_ids'] == sorted([a, b])
    store.approve(p, correction['id'])
    assert {i['id']: i['state'] for i in store.knowledge(p)['items']} == {a: 'current', b: 'needs_review'}


def test_batch_cannot_make_current_items_depend_on_new_unresolved_question(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    a = add(store, p, 0, 'a')
    b = add(store, p, 1, 'b', depends_on=[a])
    pending = store.propose(p, Proposal(base_revision=2, idempotency_key='question', summary='Unknown support', operations=[
        {'op':'upsert', 'id':a, 'title':'Unknown source', 'body':'Synthetic', 'kind':'question'},
        {'op':'upsert', 'id':b, 'title':'Unsupported conclusion', 'body':'Synthetic', 'kind':'fact', 'depends_on':[a]}]))
    assert b in pending['impact']['review_required_ids']
    store.approve(p, pending['id'])
    states = {item['id']: item['state'] for item in store.knowledge(p)['items']}
    assert states == {a:'unresolved', b:'needs_review'}



