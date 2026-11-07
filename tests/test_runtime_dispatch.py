"""Synthetic-only dispatch verification; no owner profiles or live inference."""
import json
import threading

import pytest

from knowledge_hub import cli_connections
from knowledge_hub.connections import Connections
from knowledge_hub.core import DomainError
from knowledge_hub.curator_runtime import CuratorRuntime
from knowledge_hub.store import Store


def draft():
    return {'summary': 'Synthetic', 'operations': [
        {'title': 'Sky', 'body': 'Blue', 'kind': 'fact', 'quote': 'sky is blue'}]}


def runtime_for(tmp_path, connection, *, discover=None):
    connections = Connections(Store(tmp_path), discover=discover or (lambda name: '/synthetic/bin/' + name))
    connections.confirm({'connection': connection, 'model': 'synthetic/model'}, consent=True, human=True)
    # Any CLI attempt to access the app's key vault is an error.
    def no_vault():
        raise AssertionError('CLI must never query the credential vault')
    connections._vault = no_vault
    return CuratorRuntime(connections.store, connections), connections


@pytest.mark.parametrize('connection', ['copilot', 'opencode'])
def test_cli_check_dispatches_exact_consented_adapter_and_reads_pending(tmp_path, monkeypatch, connection):
    calls = []
    class Adapter:
        def __init__(self, selected, root, *, executable, cancel):
            calls.append((selected, root, executable, cancel))
        def complete(self, model, key, packet, *, consented):
            calls.append((model, key, packet, consented))
            return draft()
    monkeypatch.setattr(cli_connections, 'CLIAdapter', Adapter)
    runtime, connections = runtime_for(tmp_path, connection)
    with pytest.raises(DomainError, match='approval_required'):
        runtime.check()
    assert not calls
    assert runtime.check(human=True) == {'status': 'checked', 'synthetic': True,
                                        'proposal_status': 'pending', 'accepted_count': 0}
    assert calls[0] == (connection, tmp_path, '/synthetic/bin/' + connection, runtime.cancelled)
    assert calls[1] == ('synthetic/model', None, {'text': 'Synthetic sky is blue',
                        'intent': 'Add synthetic knowledge; proposal only.'}, True)
    assert connections.state()['status'] == 'checked'
    assert connections.state()['enabled'] is False
    assert not list(tmp_path.glob('curator-check-*'))


def _adapter_boundary_child(pipe):
    """Install only synthetic external boundaries inside a real spawned worker."""
    import os
    from knowledge_hub import cli_models, connection_transport
    from knowledge_hub.curator_runtime import _provider_child
    assert 'OWNER_SYNTHETIC_SECRET' not in os.environ
    assert os.environ['PATH'] == '/usr/bin:/bin'
    class Router:
        def complete(self, model, key, packet):
            assert key == 'SYNTHETIC_KEY'
            assert model == 'synthetic/model'
            assert packet['text'] == 'Synthetic sky is blue'
            return draft()
    class Hermes:
        def __init__(self, root):
            assert root.is_absolute() and root.exists()
        def complete(self, model, packet):
            assert model == 'synthetic/model' and packet['text'] == 'Synthetic sky is blue'
            return draft()
    class Gemini:
        def __init__(self, root, *, executable, node_executable):
            assert root.is_absolute() and root.exists()
            assert executable == '/synthetic/bin/gemini'
            assert node_executable == '/synthetic/bin/node'
        def complete(self, model, packet, cancel, *, timeout=25):
            assert model == 'synthetic/model' and packet['text'] == 'Synthetic sky is blue'
            assert not cancel.is_set() and timeout == 25
            return draft()
    connection_transport.OpenRouterAdapter = Router
    cli_models.HermesProxyAdapter = Hermes
    cli_models.GeminiAdapter = Gemini
    _provider_child(pipe)


@pytest.mark.parametrize('connection', ['openrouter', 'hermes', 'gemini'])
def test_worker_routes_real_spawn_to_selected_adapter_only(tmp_path, monkeypatch, connection):
    from knowledge_hub import curator_runtime
    runtime, connections = runtime_for(tmp_path, connection)
    if connection == 'openrouter':
        class Vault:
            def get(self, name):
                assert name == connections.credential_name()
                return 'SYNTHETIC_KEY'
        connections._vault = lambda: Vault()
    monkeypatch.setenv('OWNER_SYNTHETIC_SECRET', 'must not inherit')
    actual = curator_runtime.bounded_inference
    calls = []
    def spawn(*args, **kwargs):
        calls.append(kwargs)
        return actual(*args, **kwargs, target=_adapter_boundary_child)
    monkeypatch.setattr(curator_runtime, 'bounded_inference', spawn)
    assert runtime.check(human=True)['proposal_status'] == 'pending'
    assert len(calls) == 1
    assert connections.state()['status'] == 'checked'
    assert connections.state()['enabled'] is False


def _failing_adapter_child(pipe):
    from knowledge_hub import cli_models
    from knowledge_hub.curator_runtime import _provider_child
    class Gemini:
        def __init__(self, *args, **kwargs):
            pass
        def complete(self, model, *args, **kwargs):
            if model == 'untrusted':
                raise DomainError('SYNTHETIC_PRIVATE_SECRET', 200)
            raise DomainError('unsupported_cli_version', 409)
    cli_models.GeminiAdapter = Gemini
    _provider_child(pipe)


@pytest.mark.parametrize('model,code,status', [('gemini-2.5-flash', 'unsupported_cli_version', 409),
                                             ('untrusted', 'curator_execution_failed', 502)])
def test_worker_preserves_only_safe_diagnostic_errors(tmp_path, model, code, status):
    from knowledge_hub.curator_runtime import bounded_inference
    with pytest.raises(DomainError, match=code) as error:
        bounded_inference(tmp_path, model, None, {'text': 'Synthetic'}, threading.Event(),
                          connection='gemini', executable='/synthetic/gemini', node_executable='/synthetic/node',
                          target=_failing_adapter_child)
    assert error.value.status == status


# Supplemental acceptance: actual adapter/process paths, synthetic providers only.
@pytest.mark.parametrize('connection,model', [('copilot', 'gpt-5.4'), ('opencode', 'synthetic/fixture-model')])
def test_runtime_actual_native_cli_to_loopback_proposal(tmp_path, monkeypatch, connection, model):
    from test_cli_connections import provider
    actual = cli_connections.CLIAdapter
    with provider() as (url, calls):
        def isolated(selected, root, **kwargs):
            return actual(selected, root, fixture_url=url, **kwargs)
        monkeypatch.setattr(cli_connections, 'CLIAdapter', isolated)
        import shutil
        runtime, connections = runtime_for(tmp_path, connection, discover=shutil.which)
        connections.confirm({'connection': connection, 'model': model}, consent=True, human=True)
        assert runtime.check(human=True)['proposal_status'] == 'pending'
    assert calls and all(not body.get('tools') for _, body in calls)
    expected = 'fixture-model' if connection == 'opencode' else model
    assert all(body['model'] == expected for _, body in calls)
    assert connections.state()['enabled'] is False


def test_runtime_actual_hermes_loopback_checks_and_cancels(tmp_path):
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from knowledge_hub.cli_auth import hermes_port
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(body)
            if len(calls) == 2:
                entered.set()
                release.wait(10)
            data = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(draft())}}]}).encode()
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', hermes_port(tmp_path)), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    runtime, connections = runtime_for(tmp_path, 'hermes')
    errors = []
    def check():
        try:
            runtime.check(human=True)
        except DomainError as error:
            errors.append(error.code)
    worker = threading.Thread(target=check)
    try:
        assert runtime.check(human=True)['proposal_status'] == 'pending'
        connections.enable(True, human=True)
        worker.start()
        assert entered.wait(5)
        started = time.monotonic()
        runtime.cancel()
        worker.join(3)
        assert not worker.is_alive() and time.monotonic() - started < 3
        assert errors == ['curator_cancelled']
        assert connections.state()['status'] == 'check_failed'
        assert connections.state()['enabled'] is False
        assert len(calls) == 2
        assert all(body['model'] == 'synthetic/model' and body['tools'] == [] and body['tool_choice'] == 'none' for body in calls)
    finally:
        release.set()
        runtime.cancel()
        if worker.ident:
            worker.join(3)
        server.shutdown()
        server.server_close()
        server_thread.join(3)
    assert not list(tmp_path.glob('curator-task-*'))


@pytest.mark.parametrize('cancelled', [False, True])
def test_runtime_actual_gemini_fixture_subprocess_cleanup(tmp_path, monkeypatch, cancelled):
    import os
    import sys
    import time
    marker = tmp_path / 'fixture-started.json'
    binary = tmp_path / 'synthetic-gemini'
    binary.write_text('#!' + sys.executable + '\n' + """
import json, os, sys, time
from pathlib import Path
if '--version' in sys.argv:
    print('0.66.0')
    raise SystemExit()
assert 'OWNER_SYNTHETIC_SECRET' not in os.environ
assert 'GEMINI_API_KEY' not in os.environ
packet = sys.stdin.read()
assert 'Synthetic sky is blue' in packet
assert '--admin-policy' in sys.argv
assert '--model' in sys.argv and 'gemini-2.5-flash' in sys.argv
""" + 'Path(' + repr(str(marker)) + ').write_text(json.dumps({"pid": os.getpid()}))\n'
        + ('time.sleep(30)\n' if cancelled else '')
        + 'print(json.dumps({"response": ' + repr(json.dumps(draft())) + ', "stats": {"models": {"gemini-2.5-flash": {}}}}))\n')
    binary.chmod(0o700)
    monkeypatch.setenv('OWNER_SYNTHETIC_SECRET', 'must not inherit')
    monkeypatch.setenv('GEMINI_API_KEY', 'must not inherit')
    runtime, connections = runtime_for(tmp_path, 'gemini', discover=lambda name: str(binary) if name == 'gemini' else sys.executable)
    connections.confirm({'connection': 'gemini', 'model': 'gemini-2.5-flash'}, consent=True, human=True)
    errors = []
    def check():
        try:
            runtime.check(human=True)
        except DomainError as error:
            errors.append(error.code)
    worker = threading.Thread(target=check)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline and worker.is_alive():
            time.sleep(0.02)
        assert marker.exists(), errors
        if cancelled:
            runtime.cancel()
        worker.join(5)
        assert not worker.is_alive()
        assert errors == (['curator_cancelled'] if cancelled else [])
        assert connections.state()['status'] == ('check_failed' if cancelled else 'checked')
        assert connections.state()['enabled'] is False
        pid = json.loads(marker.read_text())['pid']
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        runtime.cancel()
        worker.join(5)
    assert not list(tmp_path.rglob('curator-gemini-task-*'))
    assert not list(tmp_path.glob('curator-task-*'))


@pytest.mark.parametrize('connection', ['openrouter', 'copilot', 'opencode', 'hermes', 'gemini'])
def test_every_route_run_once_is_pending_only_and_requests_stay_human_pending(tmp_path, monkeypatch, connection):
    from knowledge_hub import curator_runtime
    from knowledge_hub.curator import Curator
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    runtime, connections = runtime_for(tmp_path, connection)
    calls = []
    class Adapter:
        def __init__(self, *args, **kwargs):
            pass
        def complete(self, model, key, packet, *, consented):
            calls.append(packet)
            assert key is None and consented is True
            return draft()
    monkeypatch.setattr(cli_connections, 'CLIAdapter', Adapter)
    actual = curator_runtime.bounded_inference
    def spawn(*args, **kwargs):
        calls.append(args[3])
        return actual(*args, **kwargs, target=_adapter_boundary_child)
    monkeypatch.setattr(curator_runtime, 'bounded_inference', spawn)
    if connection == 'openrouter':
        class Vault:
            def get(self, name):
                return 'SYNTHETIC_KEY'
        connections._vault = lambda: Vault()
    scope = connections.store.create_project('Synthetic route')['id']
    runtime.scope = lambda: scope
    curator = Curator(connections.store)
    curator.set_agent_access(scope, True)
    intake = Intake(connections.store)
    capture = intake.create(scope, CaptureInput(text='Synthetic sky is blue'))
    with pytest.raises(DomainError, match='curator_disabled'):
        runtime.run_once(human=True)
    assert not calls
    assert runtime.check(human=True)['status'] == 'checked'
    assert len(calls) == 1 and connections.store.changes(scope) == []
    connections.enable(True, human=True)
    result = runtime.run_once(human=True)
    assert result['status'] == 'ready_for_review' and len(calls) == 2
    assert result['result']['warehouse_change']['status'] == 'pending'
    saved = intake.get(scope, capture['id'])
    assert saved['status'] == 'proposed' and saved['result'] == result['result']
    changes = connections.store.changes(scope)
    assert len(changes) == 1 and changes[0]['status'] == 'pending'
    assert not connections.store.knowledge(scope)['items']
    request = intake.create(scope, CaptureInput(text='Clarify the synthetic sky', intent='Request something'))
    pending = runtime.run_once(human=True)
    assert pending['status'] == 'human_pending' and pending['capture_id'] == request['id']
    assert len(calls) == 2
    saved = intake.get(scope, request['id'])
    assert saved['status'] == 'pending_agent' and not saved.get('claim')
    assert len(connections.store.changes(scope)) == 1


@pytest.mark.parametrize('connection', ['openrouter', 'copilot', 'opencode', 'hermes', 'gemini'])
def test_consent_gate_precedes_every_adapter_and_vault(tmp_path, monkeypatch, connection):
    from knowledge_hub import curator_runtime
    runtime, connections = runtime_for(tmp_path, connection)
    def forbidden(*args, **kwargs):
        pytest.fail('No adapter may run without explicit consent')
    monkeypatch.setattr(cli_connections, 'CLIAdapter', forbidden)
    monkeypatch.setattr(curator_runtime, 'bounded_inference', forbidden)
    for consent in (False, 1, 'yes'):
        state = dict(connections.state(), consent=consent)
        with pytest.raises(DomainError, match='privacy_consent_required'):
            runtime._call(state, {'text': 'Synthetic'})


@pytest.mark.parametrize('connection', ['copilot', 'opencode', 'gemini'])
def test_missing_official_client_revokes_check_without_fallback(tmp_path, connection):
    runtime, connections = runtime_for(tmp_path, connection, discover=lambda name: None)
    with pytest.raises(DomainError, match='missing_cli'):
        runtime.check(human=True)
    assert connections.state()['status'] == 'check_failed'
    assert connections.state()['enabled'] is False
    assert connections.state()['last_error'] == 'missing_cli'


@pytest.mark.parametrize('phase', ['check', 'run'])
@pytest.mark.parametrize('mutation', ['key', 'reconfirm'])
def test_credential_or_reconfirmation_race_cannot_publish_readiness_or_proposal(tmp_path, phase, mutation):
    from knowledge_hub.curator import Curator
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    runtime, connections = runtime_for(tmp_path, 'openrouter')
    class Vault:
        key = None
        def put(self, name, value):
            self.key = value
        def get(self, name):
            return self.key
    vault = Vault()
    connections._vault = lambda: vault
    connections.set_key('openrouter', 'SYNTHETIC_KEY_A', human=True)
    runtime.execute = lambda *args: draft()
    runtime.check(human=True)
    connections.enable(True, human=True)
    scope = connections.store.create_project('Synthetic generation race')['id']
    Curator(connections.store).set_agent_access(scope, True)
    runtime.scope = lambda: scope
    intake = Intake(connections.store)
    capture = intake.create(scope, CaptureInput(text='Synthetic sky is blue'))
    before = connections.state()
    def replace(model, key, packet, cancel):
        assert key == 'SYNTHETIC_KEY_A'
        if mutation == 'key':
            connections.set_key('openrouter', 'SYNTHETIC_KEY_B', human=True)
        else:
            connections.confirm({'connection': 'openrouter', 'model': 'synthetic/model'}, consent=True, human=True)
        return draft()
    runtime.execute = replace
    with pytest.raises(DomainError, match='configuration_changed'):
        runtime.check(human=True) if phase == 'check' else runtime.run_once(human=True)
    after = connections.state()
    assert before['generation'] != after['generation']
    assert after['status'] != 'checked' and after['enabled'] is False
    with pytest.raises(DomainError, match='diagnostic_required'):
        connections.enable(True, human=True)
    assert not connections.store.changes(scope)
    saved = intake.get(scope, capture['id'])
    assert saved['status'] == 'pending_agent' and not saved.get('claim')
    assert 'SYNTHETIC_KEY_' not in json.dumps(after)


@pytest.mark.parametrize('phase', ['check', 'run'])
def test_stale_result_cannot_overwrite_new_generation_diagnostic(tmp_path, phase):
    from knowledge_hub.curator import Curator
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    runtime, connections = runtime_for(tmp_path, 'openrouter')
    class Vault:
        key = None
        def put(self, name, value):
            self.key = value
        def get(self, name):
            return self.key
    vault = Vault()
    connections._vault = lambda: vault
    connections.set_key('openrouter', 'SYNTHETIC_KEY_A', human=True)
    runtime.execute = lambda *args: draft()
    runtime.check(human=True)
    connections.enable(True, human=True)
    scope = connections.store.create_project('Synthetic stale result')['id']
    Curator(connections.store).set_agent_access(scope, True)
    runtime.scope = lambda: scope
    intake = Intake(connections.store)
    capture = intake.create(scope, CaptureInput(text='Synthetic sky is blue'))
    def replace_and_check(*args):
        connections.set_key('openrouter', 'SYNTHETIC_KEY_B', human=True)
        fresh = CuratorRuntime(connections.store, connections, execute=lambda *args: draft())
        fresh.check(human=True)
        connections.enable(True, human=True)
        return draft()
    runtime.execute = replace_and_check
    with pytest.raises(DomainError, match='configuration_changed'):
        runtime.check(human=True) if phase == 'check' else runtime.run_once(human=True)
    state = connections.state()
    assert state['status'] == 'checked' and state['enabled'] is True
    assert state['last_error'] is None
    assert not connections.store.changes(scope)
    assert not intake.get(scope, capture['id']).get('claim')


def test_actual_pending_readback_failure_revokes_readiness(tmp_path, monkeypatch):
    runtime, connections = runtime_for(tmp_path, 'copilot')
    class Adapter:
        def __init__(self, *args, **kwargs):
            pass
        def complete(self, *args, **kwargs):
            return draft()
    monkeypatch.setattr(cli_connections, 'CLIAdapter', Adapter)
    runtime.check(human=True)
    connections.enable(True, human=True)
    monkeypatch.setattr(Store, 'changes', lambda *args, **kwargs: [])
    with pytest.raises(DomainError, match='diagnostic_readback_failed'):
        runtime.check(human=True)
    assert connections.state()['status'] == 'check_failed'
    assert connections.state()['enabled'] is False
    with pytest.raises(DomainError, match='diagnostic_required'):
        connections.enable(True, human=True)


def test_cancel_during_synthetic_readback_cannot_mark_checked(tmp_path, monkeypatch):
    runtime, connections = runtime_for(tmp_path, 'copilot')
    class Adapter:
        def __init__(self, *args, **kwargs):
            pass
        def complete(self, *args, **kwargs):
            return draft()
    monkeypatch.setattr(cli_connections, 'CLIAdapter', Adapter)
    submit = runtime._submit
    def cancel_after_submit(*args):
        result = submit(*args)
        runtime.cancel()
        return result
    monkeypatch.setattr(runtime, '_submit', cancel_after_submit)
    with pytest.raises(DomainError, match='curator_cancelled'):
        runtime.check(human=True)
    assert connections.state()['status'] == 'check_failed'
    assert connections.state()['enabled'] is False


def test_cancel_after_adapter_validation_prevents_proposal_publication(tmp_path, monkeypatch):
    from knowledge_hub.curator import Curator
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    runtime, connections = runtime_for(tmp_path, 'copilot')
    class Adapter:
        def __init__(self, *args, **kwargs):
            pass
        def complete(self, *args, **kwargs):
            return draft()
    monkeypatch.setattr(cli_connections, 'CLIAdapter', Adapter)
    runtime.check(human=True)
    connections.enable(True, human=True)
    scope = connections.store.create_project('Synthetic cancelled publication')['id']
    Curator(connections.store).set_agent_access(scope, True)
    runtime.scope = lambda: scope
    intake = Intake(connections.store)
    capture = intake.create(scope, CaptureInput(text='Synthetic sky is blue'))
    call = runtime._call
    def cancel_after_call(*args):
        result = call(*args)
        runtime.cancel()
        return result
    monkeypatch.setattr(runtime, '_call', cancel_after_call)
    with pytest.raises(DomainError, match='curator_cancelled'):
        runtime.run_once(human=True)
    assert not connections.store.changes(scope)
    assert not intake.get(scope, capture['id']).get('claim')


def test_chatgpt_cannot_bypass_tool_denial_with_execute_injection(tmp_path):
    runtime, connections = runtime_for(tmp_path, 'chatgpt')
    runtime.execute = lambda *args: pytest.fail('Unsupported ChatGPT must not execute')
    with pytest.raises(DomainError, match='unsupported_capability'):
        runtime.check(human=True)
    assert connections.state()['status'] == 'check_failed'
    assert connections.state()['enabled'] is False


@pytest.mark.parametrize('connection', ['copilot', 'opencode'])
def test_runtime_cli_real_subprocess_cancellation_releases_claim(tmp_path, monkeypatch, connection):
    import os
    import sys
    import time
    from knowledge_hub.curator import Curator
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    marker = tmp_path / 'child-pid'
    class Adapter:
        def __init__(self, selected, root, *, executable, cancel):
            assert selected == connection
            self.cancel = cancel
        def complete(self, model, key, packet, *, consented):
            assert consented is True and key is None
            if not marker.exists():
                return draft()
            cli_connections._run([sys.executable, '-c',
                'import os,time; from pathlib import Path; Path(' + repr(str(marker)) + ').write_text(str(os.getpid())); time.sleep(30)'],
                {'PATH': '/usr/bin:/bin'}, tmp_path, cancel=self.cancel)
    monkeypatch.setattr(cli_connections, 'CLIAdapter', Adapter)
    runtime, connections = runtime_for(tmp_path, connection)
    scope = connections.store.create_project('Synthetic dispatch')['id']
    runtime.scope = lambda: scope
    Curator(connections.store).set_agent_access(scope, True)
    runtime.check(human=True)
    connections.enable(True, human=True)
    capture = Intake(connections.store).create(scope, CaptureInput(text='Synthetic sky is blue'))
    marker.write_text('waiting')
    errors = []
    def run():
        try:
            runtime.run_once(human=True)
        except DomainError as error:
            errors.append(error.code)
    worker = threading.Thread(target=run)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while marker.read_text() == 'waiting' and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.read_text() != 'waiting'
        pid = int(marker.read_text())
        runtime.cancel()
        worker.join(3)
        assert not worker.is_alive()
        assert errors == ['curator_cancelled']
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        saved = Intake(connections.store).get(scope, capture['id'])
        assert saved['status'] == 'pending_agent' and not saved.get('claim')
        assert not connections.store.changes(scope)
    finally:
        runtime.cancel()
        worker.join(3)
