"""Synthetic bounded retrieval regressions; no private knowledge."""
import json
import pytest
from fastapi.testclient import TestClient
from knowledge_hub.http import create_app
from knowledge_hub.store import Store
from knowledge_hub.shared import SharedWarehouse


def seed(path, count=120):
    store = Store(path)
    scope = SharedWarehouse(store).scope()
    project = {'id': scope}
    with store.connect() as db:
        db.execute('UPDATE projects SET purpose=? WHERE id=?', ('orientation ' * 2000, scope))
    with store.connect() as db:
        for i in range(count):
            db.execute('INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)', (
                f'item-{i:04}', project['id'], f'Apple {i:04}', 'Apple ไทย 😀 ' * 5000,
                'fact', 'current', 1, json.dumps([{'kind':'url','locator':'SECRET_SOURCE'*1000,'label':'source'}]), '[]'))
        db.execute('UPDATE projects SET revision=1 WHERE id=?', (project['id'],))
    return store, project['id']


def client(path):
    return TestClient(create_app(path, 'human', 'agent'), headers={'Authorization':'Bearer agent'})


# Supplemental boundary coverage for behavior already introduced by the tracer bullets.
@pytest.mark.parametrize('budget', [0,1023,32001])
def test_invalid_budget_is_explicit(tmp_path, budget):
    _, p = seed(tmp_path, 0)
    c = client(tmp_path)
    for suffix in ('search','context','knowledge/missing'):
        response = c.get(f'/api/agent/{suffix}', params={'max_chars':budget})
        assert response.status_code == 422 and response.json()['error'] == 'invalid_budget'


def test_default_shared_warehouse_bounds_context_pagination_and_missing_ids(tmp_path):
    store, p = seed(tmp_path)
    c = client(tmp_path)
    root = '/api/agent'
    for suffix in ('search','context'):
        response = c.get(root+'/'+suffix)
        assert response.status_code == 200 and len(response.text) <= 8000
        assert len(response.json()['items']) < 120
    assert c.get(root+'/context').json()['orientation_omitted_count'] == 115
    ids, cursor = [], ''
    while True:
        response = c.get(root+'/context', params={'q':'Apple','cursor':cursor,'max_chars':3000})
        assert len(response.text) <= 3000
        page = response.json()
        assert page['total'] == page['matched_count'] == 120
        ids.extend(i['id'] for i in page['items'])
        if not page['has_more']:
            break
        cursor = page['next_cursor']
    assert len(ids) == len(set(ids)) == 120
    # Every reader sees the same canonical data without a scope selector.
    human = TestClient(c.app)
    assert human.post('/api/session', headers={'Authorization':'Bearer human'}).status_code == 200
    assert human.get('/api/warehouse').json()['total'] == 120
    assert c.get(root+'/knowledge/item-0000').status_code == 200
    assert c.get(root+'/knowledge/missing').status_code == 404
    c.headers.clear()
    assert c.get(root+'/search').status_code == 401


def test_cursor_binding_and_identifier_never_silently_truncated(tmp_path):
    store, p = seed(tmp_path, 4)
    c = client(tmp_path)
    root = '/api/agent'
    cursor = c.get(root+'/search', params={'max_chars':1024}).json()['next_cursor']
    for suffix, params in [('search',{'q':'Apple'}),('search',{'state':'current'}),('context',{}),('search',{'cursor':'garbage'})]:
        response = c.get(root+'/'+suffix, params={'cursor':cursor, **params})
        assert response.status_code == 409 and response.json()['error'] == 'invalid_cursor'
    assert c.get(root+'/search', params={'cursor':cursor, 'max_chars':2048}).status_code == 200
    with store.connect() as db:
        db.execute("UPDATE items SET id=?,title='A' WHERE id='item-0000'", ('huge-'+'😀'*5000,))
        db.execute('UPDATE projects SET revision=2 WHERE id=?', (p,))
    assert c.get(root+'/search', params={'cursor':cursor}).status_code == 409
    response = c.get(root+'/search', params={'max_chars':1024})
    assert response.status_code == 422 and response.json()['error'] == 'budget_too_small'


def test_body_fragments_preserve_nul_quotes_backslashes_and_unicode(tmp_path):
    store, p = seed(tmp_path, 1)
    expected = ('ไทย😀\x00\"\\\n' * 1000)
    with store.connect() as db:
        db.execute("UPDATE items SET body=? WHERE id='item-0000'", (expected,))
    c = client(tmp_path)
    root = '/api/agent'
    offset, result = 0, ''
    while True:
        response = c.get(root+'/knowledge/item-0000', params={'max_chars':1024,'body_offset':offset})
        assert response.status_code == 200 and len(response.text) <= 1024
        detail = response.json()
        assert detail['body_chars'] == len(expected)
        result += detail['body']
        if detail['next_body_offset'] is None:
            break
        offset = detail['next_body_offset']
    assert result == expected
    # Continuations must not combine fragments from different canonical revisions.
    with store.connect() as db:
        db.execute('UPDATE projects SET revision=2 WHERE id=?', (p,))
    stale = c.get(root+'/knowledge/item-0000', params={'max_chars':1024, 'body_offset':offset, 'expected_revision':1})
    assert stale.status_code == 409 and stale.json()['error'] == 'stale_revision'
    assert c.get(root+'/context', params={'item_ids':['item-0000']}).json()['items'][0]['snippet_partial']


def test_search_snippet_locates_match_instead_of_unrelated_prefix(tmp_path):
    store, p = seed(tmp_path, 1)
    with store.connect() as db:
        db.execute("UPDATE items SET title='Selected',body=? WHERE id='item-0000'", ('unrelated ' * 2000 + 'needle necessary fact ' + 'tail ' * 1000,))
    response = client(tmp_path).get('/api/agent/search', params={'q':'needle'})
    assert response.status_code == 200
    item = response.json()['items'][0]
    assert 'needle necessary fact' in item['snippet']
    assert item['snippet_partial'] is True and item['detail_item_id'] == item['id']


def test_detail_body_continues_unicode_and_large_record_does_not_starve(tmp_path):
    store, p = seed(tmp_path, 3)
    with store.connect() as db:
        db.execute("UPDATE items SET title=? WHERE id='item-0000'", ('A' * 20000,))
    c = client(tmp_path)
    root = '/api/agent'
    page = c.get(root+'/search', params={'max_chars':1024}).json()
    assert page['items'][0]['id'] == 'item-0000'
    assert page['items'][0]['metadata_partial'] is True
    assert page['items'][0]['detail_item_id'] == 'item-0000'
    assert page['next_cursor']
    ids = [item['id'] for item in page['items']]
    while page['has_more']:
        response = c.get(root+'/search', params={'max_chars':1024, 'cursor':page['next_cursor']})
        assert response.status_code == 200 and len(response.text) <= 1024
        page = response.json()
        ids.extend(item['id'] for item in page['items'])
    assert ids == ['item-0000', 'item-0001', 'item-0002']
    body, offset = '', 0
    while True:
        response = c.get(root+'/knowledge/item-0000', params={'max_chars':2048,'body_offset':offset})
        assert response.status_code == 200
        assert len(response.text) <= 2048
        detail = response.json()
        assert detail['body_offset'] == offset
        assert detail['body_partial'] is True
        body += detail['body']
        if detail['next_body_offset'] is None:
            break
        assert detail['next_body_offset'] > offset
        offset = detail['next_body_offset']
    assert body == store.get_item(p, 'item-0000')['body']
    assert c.get(root+'/knowledge/item-0000', params={'body_offset':len(body)+1}).status_code == 422


def test_context_selects_dependencies_uncertainty_not_pollution(tmp_path):
    store, p = seed(tmp_path, 8)
    with store.connect() as db:
        db.execute("UPDATE items SET depends_on=?, state='needs_review' WHERE id='item-0000'", (json.dumps(['item-0001']),))
        db.execute("UPDATE items SET depends_on=? WHERE id='item-0001'", (json.dumps(['item-0000']),))
        db.execute("UPDATE items SET depends_on=?,state='unresolved',kind='question' WHERE id='item-0002'", (json.dumps(['item-0000']),))
        db.execute("UPDATE items SET state='unresolved' WHERE id='item-0007'")
    c = client(tmp_path)
    root = '/api/agent/context'
    response = c.get(root, params={'item_ids':['item-0000'], 'max_chars':8000})
    assert response.status_code == 200
    page = response.json()
    assert len(response.text) <= 8000
    assert {i['id'] for i in page['items']} == {'item-0000','item-0001','item-0002'}
    assert page['matched_count'] == 1 and page['total'] == 3
    assert {i['state'] for i in page['items']} == {'current','needs_review','unresolved'}
    assert 'project' not in page
    assert 'project_id' not in response.text
    assert all('evidence_count' in i and 'evidence' not in i for i in page['items'])
    assert 'SECRET_SOURCE' not in response.text and p not in response.text
    assert c.get(root, params={'q':'Apple','item_ids':['item-0000']}).status_code == 422
    assert c.get(root, params={'item_ids':['missing']}).status_code == 404
    default = c.get(root).json()
    assert default['orientation_only'] is True and len(default['items']) <= 5


def test_http_search_is_bounded_progressive_not_full_reader(tmp_path):
    store, p = seed(tmp_path)
    c = client(tmp_path)
    root = '/api'
    response = c.get(root+'/agent/search', params={'q':'Apple', 'max_chars':2048})
    assert response.status_code == 200
    page = response.json()
    assert len(response.text) <= 2048
    assert page['total'] == 120 and page['has_more']
    assert 0 < page['included_count'] == len(page['items']) < 120
    assert page['budget_unit'] == 'json_characters'
    assert set(page['items'][0]) >= {'id','title','kind','state','revision','snippet'}
    assert 'body' not in page['items'][0] and 'SECRET_SOURCE' not in response.text
    ids = [item['id'] for item in page['items']]
    while page['has_more']:
        page = c.get(root+'/agent/search', params={'q':'Apple', 'max_chars':2048, 'cursor':page['next_cursor']}).json()
        ids.extend(item['id'] for item in page['items'])
    assert len(ids) == len(set(ids)) == 120
    assert c.get(root+'/warehouse').json()['total'] == 120
    full = c.get(root+'/warehouse/item-0000').json()
    assert full['body'] == store.get_item(p, 'item-0000')['body']
    assert full['evidence'] == [{'kind':'url', 'locator':'SECRET_SOURCE'*1000, 'label':'source'}]
