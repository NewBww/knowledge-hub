import copy
from uuid import uuid4
import pytest
from pydantic import ValidationError
from knowledge_hub.library_models import LibraryProposal
from knowledge_hub.core import DomainError, Proposal
from test_library import setup, command, service, propose


@pytest.mark.parametrize('where', ['operations','sections','supports','links','page_ids'])
def test_duplicate_identifiers_are_rejected(where):
    cmd = command(str(uuid4()))
    if where == 'operations': cmd['operations'].append(copy.deepcopy(cmd['operations'][0]))
    if where == 'sections': cmd['operations'][0]['sections'] *= 2
    if where == 'supports': cmd['operations'][0]['sections'][0]['supports'] *= 2
    if where == 'links': cmd['operations'][0]['links'] = [str(uuid4())] * 2
    if where == 'page_ids': cmd['operations'][1]['page_ids'] *= 2
    with pytest.raises(ValidationError): LibraryProposal.model_validate(cmd)


def test_draft_gap_is_unresolved_not_current(tmp_path):
    store, p, item = setup(tmp_path)
    lib = service(store)
    cmd = command(item)
    cmd['operations'][0]['state'] = 'draft'
    cmd['operations'][0]['sections'][0]['supports'] = []
    cmd['operations'][1]['state'] = 'draft'
    lib.approve(p, propose(lib, p, cmd)['id'])
    assert lib.page(p, cmd['operations'][0]['id'])['support_state'] == 'unresolved'
    assert lib.books(p)[0]['support_state'] == 'unresolved'


def test_published_book_cannot_claim_draft_pages(tmp_path):
    store, p, item = setup(tmp_path)
    cmd = command(item)
    cmd['operations'][0]['state'] = 'draft'
    with pytest.raises(DomainError, match='unsupported_publication'): propose(service(store), p, cmd)


@pytest.mark.parametrize('state', ['superseded', 'unresolved', 'needs_review'])
def test_noncurrent_same_revision_support_is_never_current(tmp_path, state):
    store, p, item = setup(tmp_path)
    lib = service(store)
    cmd = command(item)
    lib.approve(p, propose(lib, p, cmd)['id'])
    with store.connect() as db:
        db.execute('UPDATE items SET state=? WHERE id=?', (state, item))
    expected = 'unresolved' if state == 'unresolved' else 'needs_review'
    assert lib.books(p)[0]['support_state'] == expected


def test_cannot_demote_shared_page_inside_published_book(tmp_path):
    store, p, item = setup(tmp_path)
    lib = service(store)
    cmd = command(item)
    lib.approve(p, propose(lib, p, cmd)['id'])
    op = dict(cmd['operations'][0], base_revision=1, state='draft')
    update = dict(cmd, base_revision=2, idempotency_key='demote', operations=[op])
    with pytest.raises(DomainError, match='unsupported_publication'): propose(lib, p, update)


def test_known_transitive_upstream_change_marks_shared_books_without_rewriting(tmp_path):
    # Supplemental integration: Warehouse already has cycle-safe transitive invalidation.
    store, p, root = setup(tmp_path)
    c = store.propose(p, Proposal(base_revision=1, idempotency_key='dependent', summary='Derived', operations=[dict(op='upsert', title='Derived', body='Derived', kind='fact', depends_on=[root])]))
    store.approve(p, c['id'])
    item = c['operations'][0]['id']
    lib = service(store)
    cmd = command(item, base=2)
    cmd['operations'][0]['sections'][0]['supports'][0]['revision'] = 2
    cmd['operations'].append(dict(cmd['operations'][1], id=str(uuid4()), title='Shared'))
    unrelated_page, unrelated_book = str(uuid4()), str(uuid4())
    cmd['operations'] += [dict(op='upsert_page', id=unrelated_page, base_revision=0, title='Editorial', state='published', sections=[dict(id=str(uuid4()), kind='editorial', body='Navigation')]), dict(op='upsert_book', id=unrelated_book, base_revision=0, title='Unrelated', page_ids=[unrelated_page], state='published')]
    lib.approve(p, propose(lib, p, cmd)['id'])
    # Register a cycle synthetically: real invalidation must still terminate.
    with store.connect() as db:
        import json
        db.execute('UPDATE items SET depends_on=? WHERE id=?', (json.dumps([item]), root))
    c = store.propose(p, Proposal(base_revision=3, idempotency_key='root-update', summary='Update', operations=[dict(op='upsert', id=root, title='Fact', body='New canonical', kind='fact')]))
    store.approve(p, c['id'])
    books = lib.books(p)
    assert {b['id'] for b in books if b['support_state'] == 'needs_review'} == {op['id'] for op in cmd['operations'] if op['op'] == 'upsert_book' and op['id'] != unrelated_book}
    assert lib.book(p, unrelated_book)['support_state'] == 'current'
    page = lib.page(p, cmd['operations'][0]['id'])
    assert page['sections'][0]['body'] == 'Explanation'
    assert page['sections'][0]['supports'][0]['current_revision'] == 4
