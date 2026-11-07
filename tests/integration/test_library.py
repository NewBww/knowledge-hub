"""Synthetic SQLite library fixtures; pytest basetemp must be scratch."""
import sqlite3
from uuid import uuid4
import pytest
from knowledge_hub.store import Store
from knowledge_hub.core import Proposal, DomainError


def setup(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic library')['id']
    c = store.propose(p, Proposal(base_revision=0, idempotency_key='fact', summary='Synthetic', operations=[dict(op='upsert', title='Fact', body='Canonical only', kind='fact')]))
    store.approve(p, c['id'])
    return store, p, c['operations'][0]['id']


def command(item, base=1):
    page, section, book = [str(uuid4()) for _ in range(3)]
    return dict(base_revision=base, idempotency_key=str(uuid4()), summary='Synthetic reader', operations=[
        dict(op='upsert_page', id=page, base_revision=0, title='Readable', state='published', sections=[dict(id=section, kind='factual', body='Explanation', supports=[dict(item_id=item, revision=1)])]),
        dict(op='upsert_book', id=book, base_revision=0, title='Guide', purpose='Read', overview='Intro', state='published', page_ids=[page])])


def service(store):
    from knowledge_hub.library import Library
    return Library(store)


def propose(lib, p, cmd):
    from knowledge_hub.library_models import LibraryProposal
    return lib.propose(p, LibraryProposal.model_validate(cmd))


@pytest.mark.parametrize('case,error', [('root','stale_revision'), ('entity','stale_revision'), ('support','stale_support'), ('missing','invalid_reference'), ('foreign','invalid_reference'), ('unsupported','unsupported_publication'), ('unresolved','unsupported_publication'), ('link','invalid_reference'), ('book_page','invalid_reference')])
def test_library_validates_consistent_snapshot(tmp_path, case, error):
    store, p, item = setup(tmp_path)
    lib = service(store)
    cmd = command(item)
    page, book = cmd['operations']
    if case == 'root': cmd['base_revision'] = 0
    if case == 'entity': page['base_revision'] = 4
    if case == 'support': page['sections'][0]['supports'][0]['revision'] = 2
    if case == 'missing': page['sections'][0]['supports'][0]['item_id'] = str(uuid4())
    if case == 'foreign':
        _, other, foreign = setup(tmp_path / 'other')
        page['sections'][0]['supports'][0]['item_id'] = foreign
    if case == 'unsupported': page['sections'][0]['supports'] = []
    if case == 'unresolved':
        with store.connect() as db: db.execute("UPDATE items SET state='unresolved' WHERE id=?", (item,))
    if case == 'link': page['links'] = [str(uuid4())]
    if case == 'book_page': book['page_ids'] = [str(uuid4())]
    before = store.projects(), lib.changes(p), store.knowledge(p)
    with pytest.raises(DomainError, match=error): propose(lib, p, cmd)
    assert (store.projects(), lib.changes(p), store.knowledge(p)) == before
    assert lib.books(p) == []


def test_real_reader_shares_canonical_support_and_persists_order(tmp_path):
    store, p, item = setup(tmp_path)
    lib = service(store)
    cmd = command(item)
    page = cmd['operations'][0]['id']
    other = dict(cmd['operations'][1], id=str(uuid4()), title='Second')
    cmd['operations'].append(other)
    change = propose(lib, p, cmd)
    assert lib.books(p) == []
    lib.approve(p, change['id'])
    restarted = service(Store(tmp_path))
    assert len(restarted.books(p)) == 2
    for book in restarted.books(p):
        detail = restarted.book(p, book['id'])
        assert [v['id'] for v in detail['pages']] == [page]
        assert detail['pages'][0]['sections'][0]['body'] == 'Explanation'
        assert detail['support_state'] == 'current'
    assert store.knowledge(p)['total'] == 1
    assert restarted.page(p, page)['sections'][0]['supports'][0]['item_id'] == item
