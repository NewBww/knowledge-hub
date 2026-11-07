"""Synthetic-only CLI acceptance: never uses an owner's credentials/providers."""
import json
import shutil
import threading
import os
import subprocess
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from knowledge_hub import connection_transport


def require_native_cli(connection):
    if os.environ.get('KNOWLEDGE_HUB_NATIVE_CLI_TESTS') != '1':
        pytest.skip('set KNOWLEDGE_HUB_NATIVE_CLI_TESTS=1 for native capability probes')
    if not shutil.which(connection) or not shutil.which('sandbox-exec'):
        pytest.skip(f'installed {connection} and macOS sandbox-exec required')


def synthetic_cli(tmp_path, connection, *, content=None, tool=False, malformed=False):
    """Real Mach-O process boundary; no interpreter, credentials or network."""
    from knowledge_hub.cli_connections import VERSIONS
    compiler = shutil.which('clang')
    if not shutil.which('sandbox-exec') or compiler is None:
        pytest.skip('macOS sandbox-exec and C compiler required')
    directory = tmp_path / 'cli-auth' / connection
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / 'synthetic-cli'
    reply = DRAFT if content is None else content
    event = ({'type': 'assistant.message', 'data': {'content': json.dumps(reply)}}
             if connection == 'copilot' else {'type': 'text', 'part': {'text': json.dumps(reply)}})
    if tool:
        event = {'type': 'tool.execution_start' if connection == 'copilot' else 'tool_use'}
    output = 'SYNTHETIC PRIVATE malformed event' if malformed else json.dumps(event)
    checks = ('if (!strstr(args, "--available-tools=__knowledge_hub_no_tools__")) return 11;'
              if connection == 'copilot' else
              'const char *config=getenv("OPENCODE_CONFIG_CONTENT"); if (!config || !strstr(config, "deny") || !strstr(args,"--pure")) return 12;')
    source = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
 char args[16384]="", input[65536];
 for(int i=1;i<argc;i++){strcat(args,argv[i]);strcat(args," ");}
 if(strstr(args,"--version")){puts(VERSION);return 0;}
 if(getenv("GITHUB_TOKEN") || getenv("OPENAI_API_KEY") || getenv("BASH_ENV") || getenv("HTTPS_PROXY") || getenv("COPILOT_ALLOW_ALL")) return 13;
 if(strstr(args,"sky is blue")) return 14;
 size_t n=fread(input,1,sizeof(input)-1,stdin);input[n]=0;
 if(!strstr(input,"sky is blue")) return 15;
 CHECKS
 puts(OUTPUT);return 0;
}
'''
    source = source.replace('VERSION', json.dumps(VERSIONS[connection])).replace('CHECKS', checks).replace('OUTPUT', json.dumps(output))
    subprocess.run([compiler, '-x', 'c', '-', '-o', str(binary)], input=source, text=True, capture_output=True, check=True)
    return str(binary)

DRAFT = {'summary': 'Synthetic finding', 'operations': [{'title': 'Sky', 'body': 'Synthetic sky is blue', 'kind': 'fact', 'quote': 'Synthetic sky is blue'}]}
PACKET = {'text': 'Synthetic sky is blue', 'intent': 'Add synthetic knowledge'}


def test_openrouter_privacy_constraints_never_relaxed():
    seen = []
    def transport(url, body, headers):
        seen.append(body)
        return {'model': body['model'], 'choices': [{'message': {'content': json.dumps(DRAFT)}, 'finish_reason': 'stop'}]}
    result = connection_transport.OpenRouterAdapter(transport=transport).complete('openai/gpt-5.4', 'synthetic-only', PACKET)
    assert result == DRAFT
    assert seen[0]['provider'] == {'allow_fallbacks': False, 'data_collection': 'deny', 'zdr': True, 'require_parameters': True}


@contextmanager
def provider(reply=None, tool=None):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            calls.append((self.path, {'unexpected_get': True}))
            self.send_response(400)
            self.end_headers()
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.path, body))
            content = json.dumps(DRAFT if reply is None else reply)
            message = {'role': 'assistant', 'content': content}
            finish = 'stop'
            if tool and len(calls) == 1:
                message = {'role': 'assistant', 'content': None, 'tool_calls': [
                    {'index': 0, 'id': 'synthetic-call', 'type': 'function',
                     'function': {'name': tool[0], 'arguments': json.dumps(tool[1])}}]}
                finish = 'tool_calls'
            if body.get('stream'):
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                events = [
                    {'id': 'synthetic', 'object': 'chat.completion.chunk', 'model': body['model'], 'choices': [{'index': 0, 'delta': message, 'finish_reason': None}]},
                    {'id': 'synthetic', 'object': 'chat.completion.chunk', 'model': body['model'], 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}},
                ]
                for event in events:
                    self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')
            else:
                result = {'id': 'synthetic', 'object': 'chat.completion', 'model': body['model'], 'choices': [{'index': 0, 'message': message, 'finish_reason': finish}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 10, 'total_tokens': 20}}
                data = json.dumps(result).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.skipif(not shutil.which('copilot') or not shutil.which('sandbox-exec'), reason='installed macOS CLI required')
def test_actual_copilot_payload_to_validated_draft_without_tools(tmp_path):
    require_native_cli('copilot')
    with provider() as (url, calls):
        adapter = connection_transport.CLIAdapter('copilot', tmp_path, fixture_url=url)
        result = adapter.complete('gpt-5.4', None, PACKET, consented=True)
    assert result == DRAFT
    assert calls
    assert all(body['model'] == 'gpt-5.4' for _, body in calls)
    assert all(not body.get('tools') and not body.get('functions') for _, body in calls)
    assert any(PACKET['text'] in json.dumps(body['messages']) for _, body in calls)
    assert not list((tmp_path / 'cli-tasks').iterdir())


@pytest.mark.skipif(not shutil.which('opencode') or not shutil.which('sandbox-exec'), reason='installed macOS CLI required')
def test_actual_opencode_payload_to_validated_draft_without_tools(tmp_path):
    require_native_cli('opencode')
    with provider() as (url, calls):
        adapter = connection_transport.CLIAdapter('opencode', tmp_path, fixture_url=url)
        result = adapter.complete('synthetic/fixture-model', None, PACKET, consented=True)
    assert result == DRAFT
    assert calls
    assert all(body['model'] == 'fixture-model' for _, body in calls)
    assert all(not body.get('tools') and not body.get('functions') for _, body in calls)
    assert any(PACKET['text'] in json.dumps(body['messages']) for _, body in calls)
    assert not list((tmp_path / 'cli-tasks').iterdir())


@pytest.mark.parametrize('connection,model', [('copilot', 'gpt-5.4'), ('opencode', 'synthetic/fixture-model')])
def test_actual_clis_reject_unsolicited_shell_tool_and_do_not_execute(tmp_path, connection, model):
    require_native_cli(connection)
    from knowledge_hub.core import DomainError
    marker = tmp_path / 'cli-auth' / connection / 'SHOULD_NOT_EXIST'
    with provider(tool=('bash', {'command': '/usr/bin/touch ' + str(marker), 'description': 'Synthetic forbidden write'})) as (url, calls):
        adapter = connection_transport.CLIAdapter(connection, tmp_path, fixture_url=url)
        with pytest.raises(DomainError):
            adapter.complete(model, None, PACKET, consented=True)
    assert calls
    assert not marker.exists()
    assert all(not body.get('tools') for _, body in calls)


@pytest.mark.parametrize('connection,model,tool', [
    ('copilot', 'gpt-5.4', 'view'), ('copilot', 'gpt-5.4', 'apply_patch'), ('copilot', 'gpt-5.4', 'web_fetch'),
    ('opencode', 'synthetic/fixture-model', 'read'), ('opencode', 'synthetic/fixture-model', 'write'), ('opencode', 'synthetic/fixture-model', 'webfetch')])
def test_actual_clis_deny_unsolicited_read_write_and_network(tmp_path, connection, model, tool):
    require_native_cli(connection)
    from knowledge_hub.core import DomainError
    private = tmp_path / 'UNAPPROVED_SYNTHETIC_SOURCE'
    private.write_text('UnapprovedSyntheticSourceNeverDisclose')
    marker = tmp_path / 'UNAPPROVED_WRITE'
    with provider() as (sink_url, sink_calls):
        arguments = {'filePath': str(private), 'path': str(private), 'file_path': str(private),
                     'content': 'FORBIDDEN', 'url': sink_url + '/forbidden',
                     'patch': '*** Begin Patch\n*** Add File: ' + str(marker) + '\n+FORBIDDEN\n*** End Patch'}
        with provider(tool=(tool, arguments)) as (url, calls):
            with pytest.raises(DomainError):
                connection_transport.CLIAdapter(connection, tmp_path, fixture_url=url).complete(model, None, PACKET, consented=True)
    assert sink_calls == []
    assert calls and all(not body.get('tools') for _, body in calls)
    assert not marker.exists()
    assert private.read_text() == 'UnapprovedSyntheticSourceNeverDisclose'
    assert 'UnapprovedSyntheticSourceNeverDisclose' not in json.dumps(calls)


@pytest.mark.parametrize('connection,model', [('copilot', 'gpt-5.4'), ('opencode', 'synthetic/fixture-model')])
def test_constructor_cancellation_prevents_any_request(tmp_path, connection, model):
    from knowledge_hub.core import DomainError
    cancel = threading.Event()
    cancel.set()
    with provider() as (url, calls):
        adapter = connection_transport.CLIAdapter(connection, tmp_path, executable="/usr/bin/true", fixture_url=url, cancel=cancel)
        with pytest.raises(DomainError, match='curator_cancelled'):
            adapter.complete(model, None, PACKET, consented=True)
    assert calls == []


def test_copilot_safety_settings_refuse_symlink_before_inference(tmp_path):
    from knowledge_hub.core import DomainError
    executable = synthetic_cli(tmp_path, 'copilot')
    target = tmp_path / 'outside-settings.json'
    target.write_text('synthetic unchanged')
    home = tmp_path / 'cli-auth' / 'copilot' / '.copilot'
    home.mkdir(parents=True)
    (home / 'settings.json').symlink_to(target)
    with provider() as (url, calls):
        adapter = connection_transport.CLIAdapter('copilot', tmp_path, executable=executable, fixture_url=url)
        with pytest.raises(DomainError, match='unsafe_local_storage'):
            adapter.complete('gpt-5.4', None, PACKET, consented=True)
    assert target.read_text() == 'synthetic unchanged'
    assert calls == []


def test_opencode_malformed_event_is_sanitized(tmp_path):
    from knowledge_hub.core import DomainError
    executable = synthetic_cli(tmp_path, 'opencode', malformed=True)
    adapter = connection_transport.CLIAdapter('opencode', tmp_path, executable=executable)
    with pytest.raises(DomainError, match='invalid_provider_response') as error:
        adapter.complete('openai/gpt-5.4', None, PACKET, consented=True)
    assert 'SYNTHETIC PRIVATE' not in str(error.value)


@pytest.mark.parametrize('connection,model', [('copilot', 'gpt-5.4'), ('opencode', 'synthetic/fixture-model')])
@pytest.mark.parametrize('invalid', ['tool', 'quote'])
def test_synthetic_executable_rejects_tools_and_ungrounded_quotes(tmp_path, connection, model, invalid):
    from knowledge_hub.core import DomainError
    draft = json.loads(json.dumps(DRAFT))
    draft['operations'][0]['quote'] = 'Synthetic sky is green'
    executable = synthetic_cli(tmp_path, connection, tool=invalid == 'tool', content=draft if invalid == 'quote' else None)
    with pytest.raises(DomainError, match='invalid_provider_response'):
        connection_transport.CLIAdapter(connection, tmp_path, executable=executable).complete(model, None, PACKET, consented=True)
    assert not list((tmp_path / 'cli-tasks').iterdir())


# Supplemental checks of the already implemented process and policy boundaries.
@pytest.mark.parametrize('model', ['openai/auto', 'openai/default', 'openai/latest', 'auto/gpt-5.4', 'gpt-5.4'])
def test_opencode_requires_explicit_provider_and_model_before_launch(tmp_path, monkeypatch, model):
    from knowledge_hub import cli_connections
    from knowledge_hub.core import DomainError
    def forbidden(*args, **kwargs):
        pytest.fail('must not launch for an implicit model')
    monkeypatch.setattr(cli_connections, '_run', forbidden)
    with pytest.raises(DomainError, match='invalid_configuration'):
        connection_transport.CLIAdapter('opencode', tmp_path, executable="/usr/bin/true").complete(model, None, PACKET, consented=True)


def test_fixture_sandbox_only_allows_selected_loopback_port(tmp_path):
    import subprocess
    from knowledge_hub.cli_connections import _sandbox
    task, auth = tmp_path / 'task', tmp_path / 'auth'
    task.mkdir()
    auth.mkdir()
    with provider() as (allowed, allowed_calls), provider() as (denied, denied_calls):
        port = int(allowed.split(':')[2].split('/')[0])
        policy = _sandbox('/usr/bin/curl', auth, task, fixture_port=port) + '(allow file-read* (literal "/usr/bin/curl"))'
        common = ['/usr/bin/sandbox-exec', '-p', policy, '/usr/bin/curl', '--noproxy', '*', '--max-time', '1', '-sS']
        ok = subprocess.run(common + [allowed], cwd=task, env={'HOME': str(auth)}, capture_output=True)
        blocked = subprocess.run(common + [denied], cwd=task, env={'HOME': str(auth)}, capture_output=True)
    assert ok.returncode == 0
    assert blocked.returncode != 0
    assert allowed_calls and denied_calls == []


def test_sandbox_does_not_expose_unapproved_file_metadata(tmp_path):
    import subprocess
    from knowledge_hub.cli_connections import _sandbox
    task, auth = tmp_path / 'task', tmp_path / 'auth'
    task.mkdir()
    auth.mkdir()
    private = tmp_path / 'SYNTHETIC_PRIVATE_METADATA'
    private.write_text('private fixture')
    policy = _sandbox('/usr/bin/stat', auth, task) + '(allow file-read* (literal "/usr/bin/stat"))'
    result = subprocess.run(['/usr/bin/sandbox-exec', '-p', policy, '/usr/bin/stat', str(private)], cwd=task, capture_output=True)
    assert result.returncode != 0
    assert not result.stdout


def test_sandbox_blocks_private_file_contents_writes_and_shell(tmp_path):
    import os
    import subprocess
    from knowledge_hub.cli_connections import _sandbox
    task = tmp_path / 'task'
    auth = tmp_path / 'auth'
    task.mkdir()
    auth.mkdir()
    private = tmp_path / 'PRIVATE_SYNTHETIC'
    private.write_text('synthetic private source must never enter a model request')
    for binary, args in [('/bin/cat', [str(private)]), ('/usr/bin/touch', [str(private) + '-write'])]:
        policy = _sandbox(binary, auth, task) + '(allow file-read* (literal ' + json.dumps(binary) + '))'
        result = subprocess.run(['/usr/bin/sandbox-exec', '-p', policy, binary, *args], cwd=task, env={'HOME': str(auth), 'PATH': '/usr/bin:/bin'}, capture_output=True)
        assert result.returncode != 0
        assert private.read_bytes() not in result.stdout
    assert not (tmp_path / 'PRIVATE_SYNTHETIC-write').exists()
    # exec is permitted only for this exact binary, so a shell child cannot run.
    policy = _sandbox('/usr/bin/env', auth, task) + '(allow file-read* (literal "/usr/bin/env"))'
    result = subprocess.run(['/usr/bin/sandbox-exec', '-p', policy, '/usr/bin/env', '/bin/sh', '-c', 'touch ' + str(task / 'FORBIDDEN')], cwd=task, capture_output=True)
    assert result.returncode != 0
    assert not (task / 'FORBIDDEN').exists()


def test_runner_timeout_kills_descendant_group(tmp_path):
    import os
    import sys
    import time
    from knowledge_hub.cli_connections import _run
    from knowledge_hub.core import DomainError
    marker = tmp_path / 'late-child-write'
    script = ('import os,time; pid=os.fork(); '
              f'time.sleep(1); open({str(marker)!r}, "w").write("BAD")')
    with pytest.raises(DomainError, match='curator_timeout'):
        _run([sys.executable, '-c', script], {'HOME': str(tmp_path), 'PATH': '/usr/bin:/bin'}, tmp_path, timeout=0.15)
    time.sleep(1.05)
    assert not marker.exists()


def test_runner_stderr_size_is_bounded_and_not_reflected(tmp_path):
    import sys
    from knowledge_hub.cli_connections import _run
    from knowledge_hub.core import DomainError
    with pytest.raises(DomainError, match='provider_response_size_limit') as error:
        _run([sys.executable, '-c', 'import os; os.write(2,b"synthetic-private"*100000)'], {'HOME': str(tmp_path)}, tmp_path)
    assert 'synthetic-private' not in str(error.value)


def test_runner_cancels_even_if_child_closes_output_pipes(tmp_path):
    import sys
    import time
    from knowledge_hub.cli_connections import _run
    from knowledge_hub.core import DomainError
    cancel = threading.Event()
    timer = threading.Timer(0.2, cancel.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(DomainError, match='curator_cancelled'):
            _run([sys.executable, '-c', 'import os,time; os.close(1); os.close(2); time.sleep(2)'], {'HOME': str(tmp_path)}, tmp_path, timeout=1, cancel=cancel)
    finally:
        timer.cancel()
        timer.join()
    assert time.monotonic() - started < 0.8


@pytest.mark.parametrize('connection,model', [('copilot', 'gpt-5.4'), ('opencode', 'synthetic/fixture-model')])
def test_cli_env_sanitized_and_knowledge_only_on_stdin(tmp_path, monkeypatch, connection, model):
    from knowledge_hub import cli_connections
    original = cli_connections._run
    seen = []
    monkeypatch.setenv('GITHUB_TOKEN', 'synthetic-owner-secret')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-owner-secret')
    monkeypatch.setenv('BASH_ENV', '/synthetic/owner/script')
    monkeypatch.setenv('OPENCODE_CONFIG_CONTENT', '{"permission":"allow"}')
    monkeypatch.setenv('COPILOT_ALLOW_ALL', 'true')
    monkeypatch.setenv('HTTPS_PROXY', 'http://synthetic-owner-proxy')
    def observe(argv, env, cwd, payload=b'', **kwargs):
        seen.append((argv, env))
        assert 'synthetic-owner' not in json.dumps(env)
        assert PACKET['text'] not in json.dumps(argv)
        if connection == 'opencode' and 'run' in argv:
            config = json.loads(env['OPENCODE_CONFIG_CONTENT'])
            assert config['permission'] == {'*': 'deny'}
            assert config['agent']['curator']['permission'] == {'*': 'deny'}
            assert config['model'] == config['small_model'] == config['agent']['curator']['model'] == model
            assert config['plugin'] == [] and config['mcp'] == {}
            assert '--pure' in argv
        if connection == 'copilot' and '--silent' in argv:
            assert '--available-tools=__knowledge_hub_no_tools__' in argv
            assert '--prompt' not in argv
        assert not any(key in env for key in ['GITHUB_TOKEN', 'OPENAI_API_KEY', 'BASH_ENV', 'COPILOT_ALLOW_ALL', 'HTTPS_PROXY'])
        return original(argv, env, cwd, payload, **kwargs)
    monkeypatch.setattr(cli_connections, '_run', observe)
    executable = synthetic_cli(tmp_path, connection)
    assert connection_transport.CLIAdapter(connection, tmp_path, executable=executable).complete(model, None, PACKET, consented=True) == DRAFT
    assert len(seen) == 2
    assert not list((tmp_path / 'cli-tasks').iterdir())


@pytest.mark.parametrize('connection,model', [('copilot', 'gpt-5.4'), ('opencode', 'synthetic/fixture-model')])
def test_cli_requires_consent_before_any_execution(tmp_path, monkeypatch, connection, model):
    from knowledge_hub import cli_connections
    from knowledge_hub.core import DomainError
    def forbidden(*args, **kwargs):
        pytest.fail('must not launch without explicit consent')
    monkeypatch.setattr(cli_connections, '_run', forbidden)
    with pytest.raises(DomainError, match='privacy_consent_required'):
        connection_transport.CLIAdapter(connection, tmp_path, executable="/usr/bin/true").complete(model, None, PACKET)


@pytest.mark.parametrize('connection,model', [('copilot', 'gpt-5.4'), ('opencode', 'synthetic/fixture-model')])
def test_actual_clis_reject_ungrounded_quotes(tmp_path, connection, model):
    require_native_cli(connection)
    from knowledge_hub.core import DomainError
    draft = json.loads(json.dumps(DRAFT))
    draft['operations'][0]['quote'] = 'Synthetic sky is green'
    with provider(reply=draft) as (url, calls):
        with pytest.raises(DomainError, match='invalid_provider_response'):
            connection_transport.CLIAdapter(connection, tmp_path, fixture_url=url).complete(model, None, PACKET, consented=True)
    assert calls
