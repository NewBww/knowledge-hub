import pytest
from knowledge_hub.store import Store
from knowledge_hub.core import Proposal, DomainError


def seed(store, p):
    pending = store.propose(p, Proposal(base_revision=0, idempotency_key='seed', summary='Synthetic', operations=[
        {'op':'upsert', 'title':'Synthetic apple', 'body':'A plain fact', 'kind':'fact'},
        {'op':'upsert', 'title':'Synthetic pear', 'body':'A different fact', 'kind':'fact'}]))
    store.approve(p, pending['id'])
    return pending


def test_fts_literal_search_and_project_isolation(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    other = store.create_project('Other', '')['id']
    seed(store, p)
    assert store.fts_available is True
    assert store.knowledge(p, q='apple')['total'] == 1
    assert store.knowledge(p, q='apple')['items'][0]['title'] == 'Synthetic apple'
    assert store.knowledge(other, q='apple')['total'] == 0
    assert store.knowledge(p, q='" OR 1=1; DROP TABLE items; --')['total'] == 0
    assert store.knowledge(p, state='needs_review')['total'] == 0
    assert store.knowledge(p)['total'] == 2


@pytest.mark.parametrize('query', ['\x00', 'apple\x00" OR *', '"', '* NOT OR NEAR()', ':', "' OR 1=1 --", '🍐'])
def test_search_handles_untrusted_literal_queries(tmp_path, query):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    seed(store, p)
    result = store.knowledge(p, q=query)
    assert result['total'] == len(result['items'])
    assert store.knowledge(p)['total'] == 2



def test_item_context_and_backup_restore(tmp_path):
    store = Store(tmp_path / 'original')
    p = store.create_project('Synthetic', 'Only test fixtures')['id']
    pending = seed(store, p)
    identifier = pending['operations'][0]['id']
    assert store.get_item(p, identifier)['title'] == 'Synthetic apple'
    other = store.create_project('Other', '')['id']
    with pytest.raises(DomainError, match='item_not_found'):
        store.get_item(other, identifier)
    context = store.context(p)
    assert context['revision'] == 1
    assert context['project']['purpose'] == 'Only test fixtures'
    assert len(context['current']) == 2
    assert context['needs_review'] == context['unresolved'] == []
    assert store.context(p) == context
    target = tmp_path / 'restored' / 'knowledge.sqlite3'
    store.backup(target)
    restored = Store(target.parent)
    assert restored.context(p) == context
    assert restored.knowledge(p, q='apple')['total'] == 1
    assert restored.changes(p) == store.changes(p)


def test_question_remains_unresolved_in_context(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    pending = store.propose(p, Proposal(base_revision=0, idempotency_key='question', summary='Unknown', operations=[
        {'op':'upsert', 'title':'Synthetic open question', 'body':'What remains unknown?', 'kind':'question'}]))
    store.approve(p, pending['id'])
    assert store.context(p)['current'] == []
    assert store.context(p)['unresolved'][0]['state'] == 'unresolved'


