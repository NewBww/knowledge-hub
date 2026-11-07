import asyncio
import sys
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_discovery(tmp_path):
    async def scenario():
        parameters = StdioServerParameters(command=sys.executable,
            args=['-m','knowledge_hub.cli','mcp','--data-dir',str(tmp_path)])
        with anyio.fail_after(20):
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    hello = await session.initialize()
                    assert hello.serverInfo.name == 'Knowledge Hub'
                    listing = await session.list_tools()
                    assert {tool.name for tool in listing.tools} >= {'capabilities_get','warehouse_state', 'setup_guide_get'}
                    assert 'project_create' not in {tool.name for tool in listing.tools}
                    result = await session.call_tool('capabilities_get', {})
                    assert result.structuredContent['approval_required'] is True
                    capabilities = result.structuredContent
                    assert capabilities['api_version'] == '1'
                    assert capabilities['schema_version'] == 3
                    assert capabilities['client_neutral'] is True
                    assert capabilities['approval_boundary'] == 'human_http_session_only'
                    assert 'sqlite_backup' in capabilities['supported_features']
                    assert {'library_books_pages', 'local_capture_queue', 'external_agent_curation'} <= set(capabilities['supported_features'])
                    assert 'file_ingestion' not in capabilities['unsupported_features']
                    assert {'llm_bridge', 'external_publication', 'plugin_runtime', 'arbitrary_shell', 'arbitrary_sql'} <= set(capabilities['unsupported_features'])
                    assert capabilities['data_scope'] == 'per_installation_local_directory'
                    empty = await session.call_tool('warehouse_state', {})
                    assert empty.structuredContent['item_count'] == 0
    asyncio.run(scenario())


def test_real_stdio_proposal_refusal_human_apply_and_search(tmp_path):
    from fastapi.testclient import TestClient
    from knowledge_hub.http import create_app
    from knowledge_hub.shared import SharedWarehouse
    from knowledge_hub.store import Store
    p = SharedWarehouse(Store(tmp_path)).scope()
    async def scenario():
        parameters = StdioServerParameters(command=sys.executable,
            args=['-m','knowledge_hub.cli','mcp','--data-dir',str(tmp_path)])
        with anyio.fail_after(20):
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    async def call(name, arguments):
                        result = await session.call_tool(name, arguments)
                        assert not result.isError, result
                        import json
                        return result.structuredContent if result.structuredContent is not None else json.loads(result.content[0].text)

                    request = {'base_revision':0, 'idempotency_key':'mcp-first', 'summary':'Synthetic', 'operations':[
                        {'op':'upsert', 'title':'Synthetic apple', 'body':'Plain fixture', 'kind':'fact'}]}
                    pending = await call('change_propose', {'proposal': request})
                    preview = await call('change_preview', {'change_id':pending['id']})
                    assert preview == pending
                    empty_search = await call('knowledge_search', {'q':'apple'})
                    assert empty_search['items'] == [] and empty_search['total'] == 0
                    assert await call('change_apply', {'change_id':pending['id']}) == {'error':'approval_required'}
                    assert (await call('context_get', {'project_id':p}))['revision'] == 0
                    human = TestClient(create_app(tmp_path, 'human', 'agent'))
                    human.post('/api/session', headers={'Authorization':'Bearer human'})
                    assert human.post(f"/api/changes/{pending['id']}/approve").status_code == 200
                    found = await call('knowledge_search', {'q':'apple'})
                    assert found['total'] == 1
                    item = await call('knowledge_get', {'item_id':found['items'][0]['id']})
                    assert item['id'] == found['items'][0]['id'] and item['body'] == 'Plain fixture'
                    context = await call('context_get', {'item_ids':[item['id']]})
                    assert context['revision'] == 1 and context['items'][0]['id'] == item['id']
                    accepted = human.get(f"/api/warehouse/{item['id']}").json()
                    assert accepted['body'] == item['body']
                    bad = await session.call_tool('change_propose', {'proposal':{**request, 'approved':True}})
                    assert bad.isError
                    assert (await call('context_get', {'item_ids':[item['id']]})) == context
                    forbidden = await session.call_tool('change_apply', {'change_id':pending['id'], 'approved':True})
                    assert forbidden.isError
                    schema = next(tool.inputSchema for tool in (await session.list_tools()).tools if tool.name == 'change_apply')
                    assert schema['additionalProperties'] is False
                    missing = await session.call_tool('knowledge_get', {'item_id':'missing'})
                    assert missing.isError
                    assert missing.content[0].text == 'item_not_found'

    asyncio.run(scenario())


def test_stdio_validation_errors_do_not_log_raw_inputs(tmp_path):
    async def scenario():
        parameters = StdioServerParameters(command=sys.executable,
            args=['-m','knowledge_hub.cli','mcp','--data-dir',str(tmp_path)])
        with (tmp_path / 'mcp.log').open('w+') as log, anyio.fail_after(20):
            async with stdio_client(parameters, errlog=log) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool('change_propose', {'project_id':'synthetic', 'proposal':{
                        'base_revision':0, 'idempotency_key':'bad', 'summary':'RAW_SYNTHETIC_MARKER', 'approved':True,
                        'operations':[{'op':'upsert', 'title':'Synthetic', 'body':'RAW_SYNTHETIC_MARKER', 'kind':'fact'}]}})
                    assert result.isError
                    assert result.content[0].text == 'invalid_arguments'
                    assert (await session.call_tool('warehouse_state', {})).structuredContent['item_count'] == 0
            log.seek(0)
            assert 'RAW_SYNTHETIC_MARKER' not in log.read()
        from knowledge_hub.store import Store
        with Store(tmp_path).connect() as db:
            assert db.execute('SELECT count(*) FROM changes').fetchone()[0] == 0
    asyncio.run(scenario())


