"""Synthetic-only connection/runtime regressions; never owner's credentials."""
import json
import pytest
from knowledge_hub.core import DomainError
from knowledge_hub.store import Store


class Vault:
    def __init__(self):
        self.values = {}
    def put(self, name, value):
        self.values[name] = value
    def get(self, name):
        return self.values.get(name)


def service(tmp_path, **kwargs):
    from knowledge_hub.connections import Connections
    return Connections(Store(tmp_path), vault=Vault(), **kwargs)


def test_catalog_is_six_honest_choices_and_staging_cannot_enable(tmp_path):
    connections = service(tmp_path, discover=lambda name: None)
    catalog = connections.catalog()['connections']
    assert {c['id'] for c in catalog} == {'chatgpt', 'copilot', 'openrouter', 'opencode', 'gemini', 'hermes'}
    assert all(c['availability'] == 'missing_cli' and c['install_url'].startswith('https://') for c in catalog if c['transport'] == 'cli')
    config = {'connection': 'openrouter', 'model': 'synthetic/model'}
    assert connections.stage(config)['staged'] == config
    assert connections.state()['connection'] is None
    assert connections.state()['enabled'] is False
    for payload in [dict(config, enabled=True), dict(config, api_key='SYNTHETIC_SECRET'), dict(config, command='rm -rf /'), dict(config, endpoint='http://evil.test')]:
        with pytest.raises(DomainError, match='invalid_configuration'):
            connections.stage(payload)
    assert 'SYNTHETIC_SECRET' not in ''.join(p.read_text() for p in tmp_path.glob('*.json'))
    with pytest.raises(DomainError, match='approval_required'):
        connections.confirm(config, consent=True)
    state = connections.confirm(config, consent=True, human=True)
    assert state['connection'] == 'openrouter' and state['status'] == 'sign_in_required'
    assert state['enabled'] is False
    assert connections.state() == service(tmp_path).state()


def test_pkce_state_is_one_use_bound_to_safe_callback_and_secret_is_redacted(tmp_path):
    from urllib.parse import urlparse, parse_qs
    from knowledge_hub import connections as module
    connections = service(tmp_path)
    connections.confirm({'connection': 'openrouter', 'model': 'synthetic/model'}, consent=True, human=True)
    for url in ['https://evil.test/callback', 'http://127.0.0.1:99/evil', 'http://user@localhost:80/api/curator/auth/callback', 'http://localhost.evil:80/api/curator/auth/callback']:
        with pytest.raises(DomainError, match='invalid_callback'):
            connections.start_auth('openrouter', callback_url=url, human=True)
    with pytest.raises(DomainError, match='approval_required'):
        connections.start_auth('openrouter')
    start = connections.start_auth('openrouter', callback_url='http://localhost:54321/api/curator/auth/callback', human=True)
    query = parse_qs(urlparse(start['url']).query)
    assert query['code_challenge_method'] == ['S256'] and len(query['code_challenge'][0]) == 43
    exchanged = []
    def exchange(url, body, headers=None):
        exchanged.append((url, body))
        assert body['code_challenge_method'] == 'S256'
        return {'key': 'SYNTHETIC_APP_KEY'}
    connections.exchange = exchange
    with pytest.raises(DomainError, match='invalid_auth_state'):
        connections.complete_auth('wrong', 'SYNTHETIC_CODE', human=True)
    assert not exchanged
    result = connections.complete_auth(query['state'][0], 'SYNTHETIC_CODE', human=True)
    assert result['status'] == 'unchecked' and not result['enabled']
    assert len(exchanged) == 1 and exchanged[0][0] == 'https://openrouter.ai/api/v1/auth/keys'
    with pytest.raises(DomainError, match='invalid_auth_state'):
        connections.complete_auth(query['state'][0], 'SYNTHETIC_CODE', human=True)
    persisted = ''.join(p.read_text() for p in tmp_path.glob('*.json'))
    assert 'SYNTHETIC_APP_KEY' not in persisted and 'code_verifier' not in persisted
    assert 'SYNTHETIC_APP_KEY' not in json.dumps(result)
    assert connections.vault.get(connections.credential_name()) == 'SYNTHETIC_APP_KEY'
    cli = connections.start_auth('copilot', human=True)
    assert cli['status'] in {'human_cli_handoff', 'missing_cli'}
    assert cli['command'] == ['copilot', 'login']


def test_keychain_boundary_verifies_exact_app_secret_without_subprocess(tmp_path):
    from knowledge_hub.connections import KeychainVault
    class SecurityFixture:
        kSecClass = 'class'; kSecClassGenericPassword = 'generic'; kSecAttrService = 'service'
        kSecAttrAccount = 'account'; kSecValueData = 'data'; kSecReturnData = 'return'
        kSecMatchLimit = 'limit'; kSecMatchLimitOne = 'one'
        errSecSuccess = 0; errSecItemNotFound = -25300; errSecDuplicateItem = -25299
        values = {}
        def SecItemAdd(self, query, result):
            name = query['account']
            if name in self.values:
                return (-25299, None)
            self.values[name] = query['data']
            return (0, None)
        def SecItemUpdate(self, query, change):
            self.values[query['account']] = change['data']
            return 0
        def SecItemCopyMatching(self, query, result):
            value = self.values.get(query['account'])
            return (0, value) if value else (-25300, None)
    fixture = SecurityFixture()
    vault = KeychainVault(security=fixture)
    assert vault.get('synthetic-app') is None
    vault.put('synthetic-app', 'SYNTHETIC_1')
    assert vault.get('synthetic-app') == 'SYNTHETIC_1'
    vault.put('synthetic-app', 'SYNTHETIC_2')
    assert vault.get('synthetic-app') == 'SYNTHETIC_2'
    fixture.SecItemCopyMatching = lambda *a: (-1, None)
    with pytest.raises(DomainError, match='credential_store_unavailable'):
        vault.get('synthetic-app')


def test_openrouter_text_only_exact_model_and_bounded_strict_response(tmp_path):
    from knowledge_hub.connection_transport import OpenRouterAdapter, validate_draft
    requests = []
    output = {'summary': 'Synthetic proposal', 'operations': [{'title': 'Sky', 'body': 'The sky is blue.', 'kind': 'fact', 'quote': 'sky is blue'}]}
    def transport(url, body, headers=None):
        requests.append((url, body, headers))
        return {'model': 'synthetic/model', 'choices': [{'message': {'content': json.dumps(output)}, 'finish_reason': 'stop'}]}
    adapter = OpenRouterAdapter(transport=transport)
    packet = {'text': 'Synthetic sky is blue', 'intent': 'Add knowledge'}
    draft = adapter.complete('synthetic/model', 'SYNTHETIC_KEY', packet)
    assert draft['summary'] == 'Synthetic proposal'
    url, body, headers = requests[0]
    assert url == 'https://openrouter.ai/api/v1/chat/completions'
    assert body['model'] == 'synthetic/model' and 'models' not in body
    assert body['provider']['allow_fallbacks'] is False
    assert 'tools' not in body and body['max_tokens'] == 3000
    assert headers['Authorization'] == 'Bearer SYNTHETIC_KEY'
    assert len(body['messages']) == 2
    for bad in [dict(output, approve=True), dict(output, operations=[dict(output['operations'][0], quote='invented evidence')]), dict(output, operations=[dict(output['operations'][0], command='touch /tmp/pwn')])]:
        with pytest.raises(DomainError, match='invalid_provider_response'):
            validate_draft(json.dumps(bad), packet['text'])
    with pytest.raises(DomainError, match='context_size_limit'):
        adapter.complete('synthetic/model', 'SYNTHETIC_KEY', {'text': 'x' * 24001})
    assert len(requests) == 1
    for raw in ['{"summary":"a","summary":"b","operations":[]}', 'NaN', '```json\n{}\n```']:
        with pytest.raises(DomainError, match='invalid_provider_response'):
            validate_draft(raw, packet['text'])


def test_json_transport_uses_real_synthetic_http_and_rejects_redirects(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from knowledge_hub.connection_transport import json_request
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['content-length'])))
            if self.path == '/redirect':
                self.send_response(302); self.send_header('Location', 'https://evil.test'); self.end_headers(); return
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({'echo': data}).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        base = f'http://127.0.0.1:{server.server_port}'
        assert json_request(base + '/fixture', {'synthetic': True}, allow_loopback=True) == {'echo': {'synthetic': True}}
        with pytest.raises(DomainError, match='provider_http_error'):
            json_request(base + '/redirect', {}, allow_loopback=True)
        with pytest.raises(DomainError, match='unsafe_provider_url'):
            json_request(base + '/fixture', {})
        with pytest.raises(DomainError, match='unsafe_provider_url'):
            json_request('https://evil.test/model', {})
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def configured_runtime(tmp_path, execute=None):
    from knowledge_hub.curator_runtime import CuratorRuntime
    from knowledge_hub.curator import Curator
    connections = service(tmp_path)
    scope = connections.store.create_project('Synthetic runtime')['id']
    Curator(connections.store).set_agent_access(scope, True)
    connections.confirm({'connection': 'openrouter', 'model': 'synthetic/model'}, consent=True, human=True)
    connections.set_key('openrouter', 'SYNTHETIC_KEY', human=True)
    def synthetic(model, key, packet, cancel):
        assert model == 'synthetic/model' and key == 'SYNTHETIC_KEY'
        return {'summary': 'Synthetic pending finding', 'operations': [{'title': 'Sky', 'body': 'Sky is blue.', 'kind': 'fact', 'quote': 'sky is blue'}]}
    return CuratorRuntime(connections.store, connections, scope=lambda: scope, execute=execute or synthetic), connections, scope


def test_runtime_synthetic_check_then_enable_creates_only_pending_change(tmp_path):
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    runtime, connections, scope = configured_runtime(tmp_path)
    capture = Intake(connections.store).create(scope, CaptureInput(text='Synthetic sky is blue'))
    with pytest.raises(DomainError, match='curator_disabled'):
        runtime.run_once(human=True)
    with pytest.raises(DomainError, match='diagnostic_required'):
        connections.enable(True, human=True)
    with pytest.raises(DomainError, match='approval_required'):
        runtime.check()
    checked = runtime.check(human=True)
    assert checked['status'] == 'checked' and checked['synthetic'] is True
    assert checked['proposal_status'] == 'pending' and checked['accepted_count'] == 0
    assert connections.state()['enabled'] is False
    assert len(Intake(connections.store).list(scope)) == 1
    assert connections.store.changes(scope) == []
    connections.enable(True, human=True)
    result = runtime.run_once(human=True)
    assert result['status'] == 'ready_for_review'
    assert result['result']['warehouse_change']['status'] == 'pending'
    assert not connections.store.knowledge(scope)['items']
    assert Intake(connections.store).get(scope, capture['id'])['status'] == 'proposed'
    assert runtime.run_once(human=True)['status'] == 'idle'


def test_runtime_failure_and_cancel_requeue_without_secret_or_raw_error(tmp_path):
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    calls = []
    def failed(model, key, packet, cancel):
        calls.append(packet)
        raise RuntimeError('SYNTHETIC_KEY private raw prompt')
    runtime, connections, scope = configured_runtime(tmp_path)
    capture = Intake(connections.store).create(scope, CaptureInput(text='Synthetic sky is blue'))
    # Use a valid synthetic check first, then replace only the external boundary.
    original = runtime.execute
    runtime.check(human=True); connections.enable(True, human=True)
    runtime.execute = failed
    with pytest.raises(DomainError, match='curator_execution_failed'):
        runtime.run_once(human=True)
    saved = Intake(connections.store).get(scope, capture['id'])
    assert saved['status'] == 'pending_agent' and not saved.get('claim')
    assert 'SYNTHETIC_KEY' not in json.dumps(connections.state())
    assert not connections.store.changes(scope)
    runtime.execute = original
    runtime.cancel()
    with pytest.raises(DomainError, match='curator_cancelled'):
        runtime.run_once(human=True)
    assert not Intake(connections.store).get(scope, capture['id']).get('claim')


def _synthetic_child(pipe):
    import os
    import time
    payload = json.loads(pipe.recv_bytes())
    if payload['model'] == 'sleep':
        time.sleep(20)
    assert payload['key'] == 'SYNTHETIC_KEY'
    assert os.environ.get('OWNER_FAKE_SECRET') is None
    assert os.getcwd() == os.environ['HOME']
    pipe.send_bytes(json.dumps({'summary': 'Synthetic', 'operations': [{'title': 'Sky', 'body': 'Blue', 'kind': 'fact', 'quote': 'sky is blue'}]}).encode())


def test_isolated_worker_real_process_timeout_and_cancellation(tmp_path, monkeypatch):
    import threading
    from knowledge_hub.curator_runtime import bounded_inference
    monkeypatch.setenv('OWNER_FAKE_SECRET', 'MUST_NOT_INHERIT')
    cancel = threading.Event()
    packet = {'text': 'Synthetic sky is blue'}
    result = bounded_inference(tmp_path, 'synthetic/model', 'SYNTHETIC_KEY', packet, cancel, target=_synthetic_child)
    assert result['summary'] == 'Synthetic'
    with pytest.raises(DomainError, match='curator_timeout'):
        bounded_inference(tmp_path, 'sleep', 'SYNTHETIC_KEY', packet, cancel, target=_synthetic_child, timeout=0.15)
    timer = threading.Timer(0.15, cancel.set); timer.start()
    try:
        with pytest.raises(DomainError, match='curator_cancelled'):
            bounded_inference(tmp_path, 'sleep', 'SYNTHETIC_KEY', packet, cancel, target=_synthetic_child)
    finally:
        timer.join()
    assert not list(tmp_path.glob('curator-task-*'))


def test_http_setup_handoff_never_allows_agent_auth_enable_or_secret(tmp_path):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from knowledge_hub.connections_http import register
    runtime, connections, scope = configured_runtime(tmp_path)
    app = FastAPI()
    @app.middleware('http')
    async def fixture_authorization(request: Request, call_next):
        request.state.human = request.headers.get('x-synthetic-human') == 'yes'
        return await call_next(request)
    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({'error': error.code}, status_code=error.status)
    register(app, connections.store, connections=connections, runtime=runtime)
    client = TestClient(app, base_url='http://localhost:54321')
    assert client.get('/api/curator/catalog').status_code == 200
    assert client.get('/api/curator').json()['enabled'] is False
    for path, body in [('auth/start', {'connection': 'openrouter'}), ('enable', {'enabled': True}), ('auth/key', {'connection': 'openrouter', 'key': 'SYNTHETIC_2'}), ('check', {}), ('run', {})]:
        response = client.post('/api/curator/' + path, json=body)
        assert response.status_code == 403 and response.json() == {'error': 'approval_required'}
    human = {'x-synthetic-human': 'yes'}
    proposed = {'connection': 'copilot', 'model': 'synthetic/model'}
    staged = client.post('/api/curator/config', json={'configuration': proposed}, headers=human)
    assert staged.status_code == 200 and connections.state()['connection'] == 'openrouter'
    assert client.post('/api/curator/auth/start', json={'connection': 'openrouter', 'command': 'sh'}, headers=human).status_code == 422
    start = client.post('/api/curator/auth/start', json={'connection': 'openrouter'}, headers=human)
    from urllib.parse import unquote
    assert start.status_code == 200 and '/curator-auth/callback' in unquote(start.json()['url'])
    assert client.get('/curator-auth/callback?state=bad&code=SYNTHETIC').status_code == 403
    response = client.post('/api/curator/check', json={}, headers=human)
    assert response.status_code == 200 and response.json()['synthetic'] is True
    assert client.post('/api/curator/enable', json={'enabled': True}, headers=human).json()['enabled'] is True
    assert client.post('/api/curator/enable', json={'enabled': False}, headers=human).json()['enabled'] is False
    assert app.state.connections is connections and app.state.curator_runtime is runtime
    assert app.state.runtime is runtime
    assert client.post('/api/curator/check', json={}, headers=human).status_code == 200


def test_runtime_handles_extracted_file_text_but_never_turns_a_request_into_facts(tmp_path):
    import base64
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    runtime, connections, scope = configured_runtime(tmp_path)
    runtime.check(human=True); connections.enable(True, human=True)
    intake = Intake(connections.store)
    file_capture = intake.create(scope, CaptureInput(files=[{'name': 'folder/source.txt', 'media_type': 'text/plain', 'content_base64': base64.b64encode(b'Synthetic sky is blue').decode()}]))
    assert runtime.run_once(human=True)['status'] == 'ready_for_review'
    request = intake.create(scope, CaptureInput(text='Make me a book about the sky', intent='Request something'))
    pending_before = len(connections.store.changes(scope))
    result = runtime.run_once(human=True)
    assert result['status'] == 'human_pending' and result['reason'] == 'request_requires_external_agent'
    assert len(connections.store.changes(scope)) == pending_before
    saved = intake.get(scope, request['id'])
    assert saved['status'] == 'pending_agent' and not saved.get('claim')


def test_failed_recheck_revokes_prior_readiness(tmp_path):
    runtime, connections, scope = configured_runtime(tmp_path)
    runtime.check(human=True); connections.enable(True, human=True)
    runtime.execute = lambda *a: {'summary': 'Untrusted', 'operations': [{'title': 'Fake', 'body': 'Fake', 'kind': 'fact', 'quote': 'NOT IN THE SOURCE'}]}
    with pytest.raises(DomainError, match='invalid_provider_response'):
        runtime.check(human=True)
    state = connections.state()
    assert state['enabled'] is False and state['status'] == 'check_failed'
    assert state['last_error'] == 'invalid_provider_response'


def test_auth_callback_access_log_filter_drops_sensitive_query():
    import logging
    from knowledge_hub.connections_http import AuthCallbackLogFilter
    record = logging.LogRecord('uvicorn.access', 20, '', 1, '%s - "%s %s HTTP/%s" %d',
                               ('127.0.0.1', 'GET', '/curator-auth/callback?state=SYNTHETIC_STATE&code=SYNTHETIC_CODE', '1.1', 200), None)
    assert AuthCallbackLogFilter().filter(record) is True
    assert 'SYNTHETIC_CODE' not in record.getMessage() and 'SYNTHETIC_STATE' not in record.getMessage()


def test_auth_start_requires_confirmed_destination_and_rejects_control_url(tmp_path):
    connections = service(tmp_path)
    callback = 'http://localhost:54321/curator-auth/callback'
    with pytest.raises(DomainError, match='configuration_confirmation_required'):
        connections.start_auth('openrouter', callback_url=callback, human=True)
    connections.confirm({'connection': 'openrouter', 'model': 'synthetic/model'}, consent=True, human=True)
    with pytest.raises(DomainError, match='invalid_callback'):
        connections.start_auth('openrouter', callback_url=callback + '\n', human=True)


def _external_claim_process(root, scope, capture_id, snapshot, barrier, pipe):
    from pathlib import Path
    from knowledge_hub.curator import Curator
    try:
        curator = Curator(Store(Path(root)))
        barrier.wait(timeout=10)
        curator.claim(scope, capture_id, 'external-agent-process', snapshot, 0)
        pipe.send('claimed')
    except DomainError as error:
        pipe.send(error.code)
    finally:
        pipe.close()


def test_supplemental_app_and_external_process_share_one_claim(tmp_path):
    # Existing claim semantics, exercised through the newly implemented runtime.
    import multiprocessing
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    runtime, connections, scope = configured_runtime(tmp_path)
    runtime.check(human=True); connections.enable(True, human=True)
    capture = Intake(connections.store).create(scope, CaptureInput(text='Synthetic sky is blue'))
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    barrier = context.Barrier(2)
    process = context.Process(target=_external_claim_process, args=(str(tmp_path), scope, capture['id'], capture['snapshot_sha256'], barrier, child))
    process.start(); child.close()
    try:
        barrier.wait(timeout=10)
        app_result = runtime.run_once(human=True)
        assert parent.poll(10)
        external = parent.recv()
        process.join(timeout=10)
        assert process.exitcode == 0
        assert (app_result['status'], external) in {('idle', 'claimed'), ('ready_for_review', 'capture_claimed'), ('ready_for_review', 'capture_already_proposed')}
        changes = connections.store.changes(scope)
        assert len(changes) == (1 if app_result['status'] == 'ready_for_review' else 0)
        assert not connections.store.knowledge(scope)['items']
    finally:
        if process.is_alive():
            process.kill(); process.join(timeout=2)
        parent.close(); process.close()


def test_supplemental_cli_choices_require_checks_even_when_installed(tmp_path):
    connections = service(tmp_path, discover=lambda name: '/synthetic/fixed/' + name if name else None)
    for item in connections.catalog()['connections']:
        if item['transport'] == 'cli':
            supported = item['id'] != 'chatgpt'
            assert item['availability'] == ('sign_in_required' if supported else 'unsupported_capability')
            connections.confirm({'connection': item['id'], 'model': 'synthetic/model'}, consent=True, human=True)
            with pytest.raises(DomainError, match='diagnostic_required'):
                connections.enable(True, human=True)
            handoff = connections.start_auth(item['id'], human=True)
            assert handoff['status'] == 'human_cli_handoff' and handoff['readiness'] == 'not_checked'
            assert handoff['automatic_execution'] is False


def test_supplemental_runtime_respects_revoked_source_access_before_egress(tmp_path):
    from knowledge_hub.curator import Curator
    runtime, connections, scope = configured_runtime(tmp_path)
    runtime.check(human=True); connections.enable(True, human=True)
    Curator(connections.store).set_agent_access(scope, False)
    runtime.execute = lambda *a: pytest.fail('must not disclose when source access is revoked')
    with pytest.raises(DomainError, match='agent_access_disabled'):
        runtime.run_once(human=True)
