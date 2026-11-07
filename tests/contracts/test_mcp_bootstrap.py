"""Initialized real SDK subprocess checks against isolated synthetic data only."""
import asyncio
import json
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def run_client(path, scenario):
    async def connected():
        parameters = StdioServerParameters(command=sys.executable,
            args=['-m', 'knowledge_hub.cli', 'mcp', '--data-dir', str(path)])
        with anyio.fail_after(30):
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await scenario(session)
    asyncio.run(connected())


def payload(result):
    assert not result.isError, result
    return result.structuredContent or json.loads(result.content[0].text)


def test_fresh_install_discovers_versioned_bootstrap_without_configuration(tmp_path):
    async def scenario(session):
        tools = {tool.name: tool for tool in (await session.list_tools()).tools}
        assert {'setup_guide_get', 'setup_status', 'setup_catalog', 'setup_stage'} <= tools.keys()
        resources = (await session.list_resources()).resources
        assert 'knowledgehub://setup' in {str(resource.uri) for resource in resources}
        guide = payload(await session.call_tool('setup_guide_get', {}))
        assert guide['guide_version'] == '1'
        assert guide['resource_uri'] == 'knowledgehub://setup'
        resource = await session.read_resource('knowledgehub://setup')
        assert json.loads(resource.contents[0].text) == guide
        assert guide['human_only'] == ['authentication', 'disclosure_consent', 'enable_processing',
                                       'grant_access', 'accept_proposals']
        assert guide['workflow'] == ['inspect_state', 'propose_connection_and_one_model',
                                     'human_auth_and_consent', 'synthetic_check', 'read_back_readiness']
        assert set(guide['connections']) == {'chatgpt', 'copilot', 'openrouter', 'opencode', 'gemini', 'hermes'}
        assert guide['diagnostics']['owner_data_allowed'] is False
        assert guide['operations']['setup_stage']['input'] == {'connection': 'string', 'model': 'string'}
        assert 'setup_enable' not in tools and 'setup_auth' not in tools
        assert 'setup_approve' not in tools and 'agent_access_set' not in tools
        for name in ('setup_guide_get', 'setup_status', 'setup_catalog'):
            assert tools[name].inputSchema['additionalProperties'] is False
            invalid = await session.call_tool(name, {'api_key': 'SYNTHETIC_NOT_A_SECRET'})
            assert invalid.isError and invalid.content[0].text == 'invalid_arguments'
    run_client(tmp_path, scenario)


def test_discovery_and_empty_reads_need_no_project_selection(tmp_path):
    async def scenario(session):
        tools = {tool.name: tool for tool in (await session.list_tools()).tools}
        assert 'project_create' not in tools
        for name, tool in tools.items():
            assert 'project_id' not in tool.inputSchema.get('required', []), name
            if 'project_id' in tool.inputSchema.get('properties', {}):
                assert tool.inputSchema['properties']['project_id']['deprecated'] is True
                assert 'ignored' in tool.inputSchema['properties']['project_id']['description']
        capabilities = payload(await session.call_tool('capabilities_get', {}))
        assert capabilities['schema_version'] == 3
        assert 'project_metadata' not in capabilities['supported_features']
        assert {'shared_warehouse', 'agent_bootstrap_v1'} <= set(capabilities['supported_features'])
        assert capabilities['setup_guide_uri'] == 'knowledgehub://setup'
        state = payload(await session.call_tool('warehouse_state', {}))
        assert state['revision'] == 0
        assert state['item_count'] == state['review_count'] == state['book_count'] == 0
        for name in ('knowledge_search', 'context_get', 'library_list'):
            result = await session.call_tool(name, {})
            assert not result.isError, result
            assert result.structuredContent is None
            assert len(result.content) == 1
            body = json.loads(result.content[0].text)
            assert 'project' not in body and 'project_id' not in body
        refused = payload(await session.call_tool('change_apply', {'change_id': 'synthetic'}))
        assert refused == {'error': 'approval_required'}
        capture = await session.call_tool('capture_list', {})
        assert capture.isError and capture.content[0].text == 'agent_access_disabled'
    run_client(tmp_path, scenario)


def test_setup_stages_only_nonsecret_selection_and_never_grants_authority(tmp_path):
    async def scenario(session):
        initial = payload(await session.call_tool('setup_status', {}))
        assert initial['status'] == 'unconfigured'
        assert initial['enabled'] is False and initial['consent'] is False
        catalog = payload(await session.call_tool('setup_catalog', {}))
        assert {choice['id'] for choice in catalog['connections']} == {
            'chatgpt', 'copilot', 'openrouter', 'opencode', 'gemini', 'hermes'}
        assert all(choice['availability'] != 'ready' for choice in catalog['connections'])
        staged = payload(await session.call_tool('setup_stage', {'connection': 'openrouter', 'model': 'synthetic/model-1'}))
        assert staged['staged'] == {'connection': 'openrouter', 'model': 'synthetic/model-1'}
        assert staged['connection'] is None and staged['model'] is None
        assert staged['enabled'] is False and staged['consent'] is False
        assert payload(await session.call_tool('setup_status', {})) == staged
        for extra in ('api_key', 'token', 'secret', 'enabled', 'approved', 'consent', 'human', 'command', 'path'):
            bad = await session.call_tool('setup_stage', {'connection': 'openrouter', 'model': 'synthetic/model-1', extra: True})
            assert bad.isError and bad.content[0].text == 'invalid_arguments'
        for model in ('auto', 'default', 'latest', 'model with spaces', '../bad;command'):
            bad = await session.call_tool('setup_stage', {'connection': 'openrouter', 'model': model})
            assert bad.isError and bad.content[0].text == 'invalid_configuration'
        for name in ('setup_enable', 'setup_auth', 'setup_approve', 'set_agent_access', 'setup_shell'):
            bad = await session.call_tool(name, {})
            assert bad.isError and bad.content[0].text == 'unknown_tool'
        assert payload(await session.call_tool('setup_status', {})) == staged
        assert payload(await session.call_tool('warehouse_state', {}))['item_count'] == 0
    run_client(tmp_path, scenario)


def test_setup_status_never_exports_unrelated_configuration_fields(tmp_path):
    marker = 'SYNTHETIC_PRIVATE_FIELD'
    (tmp_path / 'curator-connection.json').write_text(json.dumps({
        'connection': None, 'model': None, 'enabled': False, 'consent': False,
        'status': 'unconfigured', 'last_error': None, 'api_key': marker,
        'internal': {'token': marker},
        'staged': {'connection': 'openrouter', 'model': 'synthetic/model-1', 'secret': marker}}))
    async def scenario(session):
        status = payload(await session.call_tool('setup_status', {}))
        assert marker not in json.dumps(status)
        assert 'api_key' not in status and 'internal' not in status
        assert status['staged'] == {'connection': 'openrouter', 'model': 'synthetic/model-1'}
    run_client(tmp_path, scenario)


def test_legacy_capture_grant_cannot_become_shared_access_via_compatibility_argument(tmp_path):
    """Supplemental migration/authority characterization using real local services."""
    from knowledge_hub.curator import Curator
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    from knowledge_hub.shared import SharedWarehouse
    from knowledge_hub.store import Store
    store = Store(tmp_path)
    legacy = store.create_project('Synthetic legacy permission', '')['id']
    capture = Intake(store).create(legacy, CaptureInput(text='Synthetic legacy source'))
    Curator(store).set_agent_access(legacy, True)

    async def scenario(session):
        for arguments in ({}, {'project_id': legacy}, {'project_id': 'not-a-permission'}):
            denied = await session.call_tool('capture_list', arguments)
            assert denied.isError and denied.content[0].text == 'agent_access_disabled'
        state = payload(await session.call_tool('warehouse_state', {}))
        assert state['migration']['agent_reconsent_required'] is True
        # Trusted synthetic human fixture grants the new shared permission explicitly.
        Curator(store).set_agent_access(SharedWarehouse(store).scope(), True)
        listing = payload(await session.call_tool('capture_list', {}))
        assert listing['total'] == 1 and listing['captures'][0]['id'] == capture['id']
        assert payload(await session.call_tool('capture_list', {'project_id': legacy})) == listing
    run_client(tmp_path, scenario)
