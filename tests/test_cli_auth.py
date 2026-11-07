"""Synthetic profiles only. No owner's credentials or model calls."""
import json
from knowledge_hub.connections import Connections
from knowledge_hub.store import Store


def test_official_signin_handoffs_use_app_owned_profiles_without_running_clients(tmp_path):
    connections = Connections(Store(tmp_path), discover=lambda name: '/fixed/' + name if name else None)
    expected = {'chatgpt': ('CODEX_HOME', ['codex', 'login']),
                'gemini': ('GEMINI_CLI_HOME', ['gemini']),
                'hermes': ('HERMES_HOME', ['hermes', 'portal'])}
    for provider, (variable, command) in expected.items():
        handoff = connections.start_auth(provider, human=True)
        assert handoff['command'] == command
        assert handoff['environment'][variable].startswith(str(tmp_path))
        assert handoff['environment']['HOME'].startswith(str(tmp_path))
        assert handoff['automatic_execution'] is False
        assert handoff['readiness'] == 'not_checked'
        assert handoff['steps']
    assert connections.state()['enabled'] is False
    assert not list(tmp_path.rglob('auth.json'))
    assert 'is not yet verified and is blocked' not in connections.catalog()['disclosure']


def test_copilot_and_opencode_signin_profiles_match_native_adapter_storage(tmp_path):
    connections = Connections(Store(tmp_path), discover=lambda name: '/fixed/' + name if name else None)
    for provider in ['copilot', 'opencode']:
        handoff = connections.start_auth(provider, human=True)
        assert handoff['environment']['HOME'] == str(tmp_path / 'cli-auth' / provider)
        if provider == 'copilot':
            assert handoff['environment']['COPILOT_HOME'] == str(tmp_path / 'cli-auth/copilot/.copilot')
        else:
            assert handoff['environment']['XDG_DATA_HOME'] == str(tmp_path / 'cli-auth/opencode/data')


def test_auth_handoff_includes_official_cli_node_runtime_directory(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, 'which', lambda name: '/synthetic-runtime/node' if name == 'node' else None)
    connections = Connections(Store(tmp_path), discover=lambda name: '/fixed/' + name if name else None)
    handoff = connections.start_auth('gemini', human=True)
    assert '/synthetic-runtime' in handoff['steps'][0][2].split('=', 1)[1].split(':')


def test_catalog_distinguishes_adapter_capability_from_unchecked_authentication(tmp_path):
    connections = Connections(Store(tmp_path), discover=lambda name: '/fixed/' + name if name else None)
    catalog = {item['id']: item for item in connections.catalog()['connections']}
    for provider in ['hermes', 'gemini', 'copilot', 'opencode']:
        assert catalog[provider]['capability'] == 'bounded_text'
        assert catalog[provider]['availability'] == 'sign_in_required'
        assert catalog[provider]['readiness'] == 'not_checked'
        assert connections.start_auth(provider, human=True)['execution'] == 'diagnostic_required'
    assert catalog['chatgpt']['capability'] == 'tool_denial_unverified'
    assert 'deny-all' in catalog['chatgpt']['reason']
    assert catalog['gemini']['supported_models'] == ['gemini-2.5-flash', 'gemini-2.5-pro']
    assert connections.state()['enabled'] is False


def test_enable_supports_only_implemented_routes_after_checked_diagnostic(tmp_path):
    import pytest
    from knowledge_hub.core import DomainError
    connections = Connections(Store(tmp_path), discover=lambda name: '/fixed/' + name if name else None)
    for provider in ['hermes', 'gemini', 'copilot', 'opencode', 'openrouter', 'chatgpt']:
        connections.confirm({'connection': provider, 'model': 'gemini-2.5-pro' if provider == 'gemini' else 'synthetic/model'}, consent=True, human=True)
        with pytest.raises(DomainError, match='diagnostic_required'):
            connections.enable(True, human=True)
        # Synthetic persisted diagnostic state; the real runtime writes this only after readback.
        state = connections.state(); state['status'] = 'checked'; connections._save(state)
        if provider == 'chatgpt':
            with pytest.raises(DomainError, match='diagnostic_required'):
                connections.enable(True, human=True)
        else:
            assert connections.enable(True, human=True)['enabled'] is True
        connections.enable(False, human=True)


def test_hermes_model_only_proxy_sends_exact_model_no_tools_with_real_local_server(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from knowledge_hub import cli_models
    from knowledge_hub.cli_auth import hermes_port
    requests = []
    draft = {'summary': 'Synthetic', 'operations': [{'title': 'Sky', 'body': 'Blue', 'kind': 'fact', 'quote': 'sky is blue'}]}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['content-length'])))
            requests.append((self.path, body, self.headers.get('Authorization')))
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({'model': 'synthetic/model', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(draft)}}]}).encode())
    server = ThreadingHTTPServer(('127.0.0.1', hermes_port(tmp_path)), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        output = cli_models.HermesProxyAdapter(tmp_path).complete('synthetic/model', {'text': 'Synthetic sky is blue'})
        assert output == draft
        path, body, authorization = requests[0]
        assert path == '/v1/chat/completions'
        assert body['model'] == 'synthetic/model' and 'models' not in body
        assert body['tool_choice'] == 'none' and body['tools'] == []
        assert body['stream'] is False and body['max_tokens'] == 3000
        assert authorization == 'Bearer knowledge-hub-proxy'
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_gemini_execution_uses_admin_deny_all_and_only_selected_model(tmp_path, monkeypatch):
    import os
    import threading
    from pathlib import Path
    from knowledge_hub import cli_models
    binary = tmp_path / 'gemini-fixture'
    # A real child process verifies the launch contract before returning synthetic output.
    binary.write_text('''#!/usr/bin/env python3
import json, os, sys
if '--version' in sys.argv:
    print('0.66.0'); raise SystemExit(0)
args = sys.argv[1:]
assert '--admin-policy' in args
policy = open(args[args.index('--admin-policy') + 1]).read()
assert 'toolName = "*"' in policy and 'decision = "deny"' in policy
settings = json.load(open(os.environ['GEMINI_CLI_SYSTEM_SETTINGS_PATH']))
assert settings['hooksConfig']['enabled'] is False
assert settings['mcp']['allowed'] == []
assert settings['modelConfigs']['customOverrides'][0]['match'] == {'overrideScope': 'core'}
assert settings['modelConfigs']['customOverrides'][0]['modelConfig']['model'] == 'gemini-2.5-pro'
assert os.environ.get('OWNER_FAKE_SECRET') is None
assert os.environ.get('GEMINI_API_KEY') is None
assert '/synthetic-runtime' in os.environ['PATH'].split(':')
assert args[args.index('--model') + 1] == 'gemini-2.5-pro'
assert '--yolo' not in args and '--resume' not in args
assert '--extensions' in args and args[args.index('--extensions') + 1] == 'none'
assert os.getcwd().startswith(os.environ['HOME'])
packet = sys.stdin.read()
assert 'Synthetic sky is blue' in packet
print(json.dumps({'response': json.dumps({'summary': 'Synthetic', 'operations': [{'title': 'Sky', 'body': 'Blue', 'kind': 'fact', 'quote': 'sky is blue'}]}), 'stats': {'models': {'gemini-2.5-pro': {}}}}))
''')
    binary.chmod(0o700)
    monkeypatch.setenv('OWNER_FAKE_SECRET', 'MUST_NOT_INHERIT')
    monkeypatch.setenv('GEMINI_API_KEY', 'MUST_NOT_INHERIT')
    # /usr/bin/env python3 is fixed test fixture; no real client/model is contacted.
    result = cli_models.GeminiAdapter(tmp_path, executable=str(binary), node_executable='/synthetic-runtime/node').complete(
        'gemini-2.5-pro', {'text': 'Synthetic sky is blue'}, threading.Event())
    assert result['summary'] == 'Synthetic'
    assert not list(tmp_path.rglob('curator-gemini-task-*'))


def test_cancelled_gemini_never_starts_any_process(tmp_path, monkeypatch):
    import subprocess
    launches = []
    original = subprocess.Popen
    def recorded(*args, **kwargs):
        launches.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', recorded)
    import threading
    import pytest
    from knowledge_hub.cli_models import GeminiAdapter
    from knowledge_hub.core import DomainError
    binary = tmp_path / 'fixture'
    marker = tmp_path / 'started'
    binary.write_text('#!/bin/sh\ntouch ' + str(marker) + '\nsleep 1\n')
    binary.chmod(0o700)
    cancel = threading.Event(); cancel.set()
    with pytest.raises(DomainError, match='curator_cancelled'):
        GeminiAdapter(tmp_path, executable=str(binary)).complete('gemini-2.5-pro', {'text': 'Synthetic'}, cancel)
    assert not marker.exists()
    assert launches == []


def test_supplemental_process_bounds_timeout_cancellation_and_output(tmp_path):
    import pytest
    import threading
    from knowledge_hub.cli_models import _run_process
    from knowledge_hub.core import DomainError
    cases = [('sleep 10', 'curator_timeout', False),
             ('sleep 10', 'curator_cancelled', True),
             ('/usr/bin/yes X', 'provider_response_size_limit', False),
             ('printf SYNTHETIC_PRIVATE_ERROR >&2; exit 1', 'cli_auth_or_execution_failed', False)]
    for index, (body, error, should_cancel) in enumerate(cases):
        binary = tmp_path / f'fixture-{index}'
        binary.write_text('#!/bin/sh\n' + body + '\n'); binary.chmod(0o700)
        cancel = threading.Event()
        timer = threading.Timer(0.05, cancel.set) if should_cancel else None
        if timer: timer.start()
        try:
            with pytest.raises(DomainError, match=error):
                _run_process([str(binary)], {'HOME': str(tmp_path), 'PATH': '/usr/bin:/bin'}, str(tmp_path), '', cancel,
                             0.2 if error == 'curator_timeout' else 3)
        finally:
            if timer: timer.join()



def _terminatable_process_fixture(root, binary):
    import threading
    from knowledge_hub.cli_models import _run_process
    try:
        _run_process([binary], {'HOME': root, 'PATH': '/usr/bin:/bin'}, root, '', threading.Event(), 10)
    except BaseException:
        pass


def test_terminating_inference_worker_does_not_leave_cli_process_alive(tmp_path):
    import multiprocessing
    import os
    import signal
    import time
    binary = tmp_path / 'fixture'
    pid_path = tmp_path / 'pid'
    binary.write_text('#!/bin/sh\necho $$ > ' + str(pid_path) + '\nsleep 10\n'); binary.chmod(0o700)
    worker = multiprocessing.get_context('spawn').Process(target=_terminatable_process_fixture, args=(str(tmp_path), str(binary)))
    worker.start()
    cli_pid = None
    try:
        deadline = time.monotonic() + 5
        while not pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pid_path.exists()
        cli_pid = int(pid_path.read_text())
        worker.terminate(); worker.join(timeout=3)
        assert not worker.is_alive()
        try:
            os.kill(cli_pid, 0)
        except ProcessLookupError:
            alive = False
        else:
            alive = True
        assert alive is False
    finally:
        if worker.is_alive(): worker.kill(); worker.join(timeout=2)
        if cli_pid:
            try: os.killpg(cli_pid, signal.SIGKILL)
            except ProcessLookupError: pass
        worker.close()


def test_missing_gemini_binary_is_a_redacted_domain_error(tmp_path):
    import pytest
    import threading
    from knowledge_hub.cli_models import GeminiAdapter
    from knowledge_hub.core import DomainError
    with pytest.raises(DomainError, match='cli_auth_or_execution_failed'):
        GeminiAdapter(tmp_path, executable=str(tmp_path / 'SYNTHETIC_PRIVATE_PATH')).complete(
            'gemini-2.5-pro', {'text': 'Synthetic'}, threading.Event())



def test_gemini_machine_admin_policies_cannot_override_app_tool_denial(tmp_path, monkeypatch):
    import pytest
    import threading
    from pathlib import Path
    from knowledge_hub.cli_models import GeminiAdapter
    from knowledge_hub.core import DomainError
    original = Path.exists
    monkeypatch.setattr(Path, 'exists', lambda path: True if str(path) == '/Library/Application Support/GeminiCli/policies' else original(path))
    with pytest.raises(DomainError, match='conflicting_cli_policy'):
        GeminiAdapter(tmp_path, executable='/must/not/execute').complete('gemini-2.5-pro', {'text': 'Synthetic'}, threading.Event())




