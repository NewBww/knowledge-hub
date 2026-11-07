"""Actual newline-delimited JSON-RPC exchanged with the installed SDK subprocess."""
import json
import select
import subprocess
import sys
from contextlib import contextmanager
from knowledge_hub.store import Store
from knowledge_hub.shared import SharedWarehouse


def seed(path, count=120):
    store = Store(path)
    scope = SharedWarehouse(store).scope()
    with store.connect() as db:
        for i in range(count):
            db.execute('INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)', (
                f'item-{i:04}', scope, f'Apple {i:04}', 'Apple ไทย 😀 ' * 5000,
                'fact', 'current', 1, '[]', '[]'))
        db.execute('UPDATE projects SET revision=1 WHERE id=?', (scope,))
    return store, scope


@contextmanager
def wire(path):
    process = subprocess.Popen([sys.executable, '-m', 'knowledge_hub.cli', 'mcp', '--data-dir', str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    counter = 0
    def send(message):
        process.stdin.write(json.dumps(message, ensure_ascii=False)+'\n')
        process.stdin.flush()
    def rpc(method, params):
        nonlocal counter
        counter += 1
        send({'jsonrpc':'2.0','id':counter,'method':method,'params':params})
        while True:
            assert select.select([process.stdout], [], [], 20)[0], 'stdio response timed out'
            line = process.stdout.readline()
            assert line, process.stderr.read()
            result = json.loads(line)
            if result.get('id') == counter:
                assert 'error' not in result, result
                return result['result'], len(line.rstrip('\n'))
    try:
        rpc('initialize', {'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'synthetic-test','version':'1'}})
        send({'jsonrpc':'2.0','method':'notifications/initialized'})
        yield rpc
    finally:
        process.terminate()
        process.communicate(timeout=10)


def call(rpc, tool, arguments):
    result, size = rpc('tools/call', {'name':tool,'arguments':arguments})
    assert not result.get('isError'), result
    assert 'structuredContent' not in result
    assert len(result['content']) == 1 and result['content'][0]['type'] == 'text'
    return json.loads(result['content'][0]['text']), size


def test_real_mcp_large_body_offset_wire_budget(tmp_path):
    store, p = seed(tmp_path, 1)
    expected = store.get_item(p, 'item-0000')['body']
    with wire(tmp_path) as rpc:
        body, offset, sizes = '', 0, []
        while True:
            detail, size = call(rpc, 'knowledge_get', {'item_id':'item-0000',
                'body_offset':offset,'max_chars':2048,'expected_revision':1})
            sizes.append(size)
            assert size <= 2048 and detail['body_offset'] == offset
            body += detail['body']
            if detail['next_body_offset'] is None:
                break
            assert detail['body_partial'] and detail['next_body_offset'] > offset
            offset = detail['next_body_offset']
        assert body == expected and len(sizes) > 1
        stale, _ = rpc('tools/call', {'name':'knowledge_get','arguments':{'project_id':p,
            'item_id':'item-0000','expected_revision':0}})
        assert stale['isError'] and stale['content'][0]['text'] == 'stale_revision'
        print(f'MCP body: {len(sizes)} segments, max wire characters={max(sizes)}')


def test_real_mcp_context_selector_cursor_and_service_equivalence(tmp_path):
    from knowledge_hub.retrieval import Retrieval
    store, p = seed(tmp_path)
    with wire(tmp_path) as rpc:
        page, size = call(rpc, 'context_get', {'item_ids':['item-0001','item-0002']})
        assert size <= 8000 and page['total'] == page['matched_count'] == 2
        assert [i['id'] for i in page['items']] == ['item-0001','item-0002']
        from knowledge_hub.shared import public
        assert page == public(Retrieval(store).context(p, item_ids=['item-0001','item-0002']))
        assert 'project' not in page and 'project_id' not in page
        search, _ = call(rpc, 'knowledge_search', {'max_chars':1024})
        cursor = search['next_cursor']
        next_page, _ = call(rpc, 'knowledge_search', {'max_chars':1024,'cursor':cursor})
        assert not {i['id'] for i in search['items']}.intersection(i['id'] for i in next_page['items'])
        bad, _ = rpc('tools/call', {'name':'knowledge_search','arguments':{'project_id':p,'q':'Apple','cursor':cursor}})
        assert bad['isError'] and bad['content'][0]['text'] == 'invalid_cursor'
        with store.connect() as db:
            db.execute('UPDATE projects SET revision=revision+1 WHERE id=?', (p,))
        stale, _ = rpc('tools/call', {'name':'knowledge_search','arguments':{'project_id':p,'cursor':cursor}})
        assert stale['isError'] and stale['content'][0]['text'] == 'invalid_cursor'


def test_real_mcp_search_wire_budget_and_schema(tmp_path):
    _, p = seed(tmp_path)
    with wire(tmp_path) as rpc:
        tools, _ = rpc('tools/list', {})
        tool = next(t for t in tools['tools'] if t['name'] == 'knowledge_search')
        assert {'max_chars','cursor'} <= set(tool['inputSchema']['properties'])
        assert 'outputSchema' not in tool
        page, size = call(rpc, 'knowledge_search', {'q':'Apple','max_chars':2048})
        assert size <= 2048
        assert page['total'] == 120 and page['has_more']
        assert 'body' not in page['items'][0]
        caps, _ = rpc('tools/call', {'name':'capabilities_get','arguments':{}})
        assert 'budgeted_agent_retrieval' in caps['structuredContent']['supported_features']
