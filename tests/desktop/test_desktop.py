import importlib
import stat
import socket
import threading
import urllib.request

import pytest
from fastapi import FastAPI

from pathlib import Path


def desktop():
    return importlib.import_module('knowledge_hub.desktop')


def test_runtime_directory_and_persistent_private_agent_token(tmp_path, monkeypatch):
    module = desktop()
    root = tmp_path / 'runtime'
    monkeypatch.setenv('KNOWLEDGE_HUB_DATA_DIR', str(root))
    assert module.resolve_data_dir() == root
    token = module.get_agent_token(root)
    assert len(token) >= 32
    assert module.get_agent_token(root) == token
    assert (root / 'agent.token').read_text().strip() == token
    assert stat.S_IMODE((root / 'agent.token').stat().st_mode) == 0o600
    assert module.resolve_data_dir(tmp_path) == tmp_path


def test_desktop_and_cli_share_exact_agent_token(tmp_path):
    from knowledge_hub.cli import load_agent_token
    token = desktop().get_agent_token(tmp_path)
    assert load_agent_token(tmp_path) == token


def test_invalid_agent_token_is_not_silently_accepted_or_replaced(tmp_path):
    path = tmp_path / 'agent.token'
    path.write_text('short')
    with pytest.raises(RuntimeError, match='Invalid agent token'):
        desktop().get_agent_token(tmp_path)
    assert path.read_text() == 'short'


def test_agent_token_refuses_symlink_without_modifying_target(tmp_path):
    root = tmp_path / 'runtime'
    root.mkdir()
    target = tmp_path / 'unrelated-secret'
    target.write_text('leave-me-alone')
    target.chmod(0o644)
    (root / 'agent.token').symlink_to(target)
    with pytest.raises((OSError, RuntimeError)):
        desktop().get_agent_token(root)
    assert target.read_text() == 'leave-me-alone'
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_loopback_server_ready_before_use_and_joined_on_exit():
    app = FastAPI()

    @app.get('/')
    def home():
        return {'ready': True}

    with desktop().LocalServer(app) as server:
        assert server.address[0] == '127.0.0.1'
        assert server.address[1] > 0
        assert server.thread.is_alive()
        assert not server.thread.daemon
        with urllib.request.urlopen(server.url, timeout=2) as response:
            assert response.status == 200
            assert b'"ready":true' in response.read()
        address = server.address
    assert not server.thread.is_alive()
    with socket.socket() as probe:
        assert probe.connect_ex(address) != 0


def test_failed_readiness_closes_socket_and_joins_thread():
    app = FastAPI()
    server = desktop().LocalServer(app, timeout=0.15)
    with pytest.raises(RuntimeError, match='readiness timed out'):
        with server:
            pytest.fail('A missing UI must never open a window')
    assert not server.thread.is_alive()
    assert server.socket.fileno() == -1


def test_launch_requires_main_thread(tmp_path):
    errors = []

    def run():
        try:
            desktop().launch(tmp_path)
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(2)
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert 'main thread' in str(errors[0])
    assert not list(tmp_path.iterdir())


def test_native_unavailable_is_explicit_not_a_browser_fallback(tmp_path, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, 'webview', None)
    with pytest.raises(RuntimeError, match='pywebview'):
        desktop().launch(tmp_path)
    assert not list(tmp_path.iterdir())


def test_native_launcher_serves_real_app_auth_and_stops_on_close(tmp_path, monkeypatch, caplog):
    import sys
    import types
    from urllib.parse import urlsplit, parse_qs

    calls, addresses, secrets_seen = [], [], []

    def create_window(title, url, **kwargs):
        assert threading.current_thread() is threading.main_thread()
        assert title == 'Knowledge Hub'
        parsed = urlsplit(url)
        addresses.append((parsed.hostname, parsed.port))
        assert parsed.hostname == '127.0.0.1'
        assert not parsed.query
        token = parse_qs(parsed.fragment)['token'][0]
        secrets_seen.append(token)
        base = f'{parsed.scheme}://{parsed.netloc}'
        with urllib.request.urlopen(base + '/', timeout=2) as response:
            assert response.status == 200
        request = urllib.request.Request(base + '/api/session', method='POST',
                                         headers={'Authorization': f'Bearer {token}'})
        with urllib.request.urlopen(request, timeout=2) as response:
            cookie = response.headers['Set-Cookie'].lower()
            assert 'httponly' in cookie
            assert 'samesite=strict' in cookie
        calls.append('window')
        return object()

    def start(**kwargs):
        assert kwargs['gui'] == 'cocoa'
        assert kwargs['debug'] is False
        assert kwargs['private_mode'] is True
        assert threading.current_thread() is threading.main_thread()
        calls.append('start-and-close')

    monkeypatch.setitem(sys.modules, 'webview.platforms.cocoa', types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(
        create_window=create_window, start=start))
    desktop().launch(tmp_path)
    assert calls == ['window', 'start-and-close']
    assert not any(t.name == 'knowledge-hub-http' for t in threading.enumerate())
    for address in addresses:
        with socket.socket() as probe:
            assert probe.connect_ex(address) != 0
    assert secrets_seen[0] != (tmp_path / 'agent.token').read_text().strip()
    assert all(secret not in caplog.text for secret in secrets_seen)


def test_missing_cocoa_cannot_silently_select_another_renderer(tmp_path, monkeypatch):
    import sys
    import types
    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'webview.platforms.cocoa', None)
    with pytest.raises(RuntimeError, match='pywebview'):
        desktop().launch(tmp_path)
    assert not list(tmp_path.iterdir())


def test_native_start_failure_cleans_server_and_hides_bootstrap_secret(tmp_path, monkeypatch, caplog):
    import sys
    import types
    from urllib.parse import urlsplit
    urls = []

    def create_window(title, url, **kwargs):
        urls.append(url)
        return object()

    def fail(**kwargs):
        raise ValueError(urls[0])

    monkeypatch.setitem(sys.modules, 'webview.platforms.cocoa', types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(create_window=create_window, start=fail))
    with pytest.raises(RuntimeError, match='Native WebKit') as caught:
        desktop().launch(tmp_path)
    assert urls[0] not in str(caught.value)
    assert urls[0] not in caplog.text
    assert caught.value.__suppress_context__
    assert not any(t.name == 'knowledge-hub-http' for t in threading.enumerate())
    parsed = urlsplit(urls[0])
    with socket.socket() as probe:
        assert probe.connect_ex((parsed.hostname, parsed.port)) != 0


def test_desktop_initializes_native_only_inside_running_webview_callback(tmp_path, monkeypatch):
    import sys
    import types
    import knowledge_hub.http as http
    import knowledge_hub.native_updater as native
    apps, initialized = [], []
    real_create = http.create_app

    def create(**kwargs):
        app = real_create(**kwargs)
        apps.append(app)
        return app

    bridge = object()

    def initialize(on_ready, on_unavailable):
        initialized.append(True)
        on_ready(bridge)

    def start(**kwargs):
        assert initialized == []
        assert apps[0].state.updater.native is None
        kwargs['func']()
        assert apps[0].state.updater.native is bridge

    monkeypatch.setattr(http, 'create_app', create)
    monkeypatch.setattr(native, 'initialize_native_updater', initialize)
    monkeypatch.setitem(sys.modules, 'webview.platforms.cocoa', types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(
        create_window=lambda *args, **kwargs: object(), start=start))
    desktop().launch(tmp_path)
    assert initialized == [True]
    assert not any(t.name == 'knowledge-hub-http' for t in threading.enumerate())


def test_desktop_native_failure_keeps_app_usable_with_explicit_reason(tmp_path, monkeypatch):
    import sys
    import types
    import knowledge_hub.http as http
    import knowledge_hub.native_updater as native
    apps = []
    real_create = http.create_app

    def create(**kwargs):
        app = real_create(**kwargs)
        apps.append(app)
        return app

    def start(**kwargs):
        kwargs['func']()
        assert apps[0].state.updater.native is None
        assert apps[0].state.updater.unavailable_reason == 'Synthetic read-only mount'

    monkeypatch.setattr(http, 'create_app', create)
    monkeypatch.setattr(native, 'initialize_native_updater',
                        lambda ready, unavailable: unavailable('Synthetic read-only mount'))
    monkeypatch.setitem(sys.modules, 'webview.platforms.cocoa', types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(
        create_window=lambda *args, **kwargs: object(), start=start))
    desktop().launch(tmp_path)


def test_fresh_install_is_empty_and_relaunch_preserves_data(tmp_path, monkeypatch):
    import http.cookiejar
    import json
    import sys
    import types
    from urllib.parse import urlsplit, parse_qs
    observations = []

    def create_window(title, url, **kwargs):
        parsed = urlsplit(url)
        base = f'{parsed.scheme}://{parsed.netloc}'
        token = parse_qs(parsed.fragment)['token'][0]
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        request = urllib.request.Request(base + '/api/session', method='POST',
                                         headers={'Authorization': f'Bearer {token}'})
        with opener.open(request, timeout=2):
            pass
        with opener.open(base + '/api/workspace', timeout=2) as response:
            state = json.load(response)
        assert state['item_count'] == state['book_count'] == 0
        with opener.open(base + '/api/captures', timeout=2) as response:
            captures = json.load(response)['captures']
        observations.append(len(captures))
        if not captures:
            request = urllib.request.Request(base + '/api/captures', method='POST',
                data=json.dumps({'text': 'Synthetic preserved capture', 'intent': 'Add knowledge'}).encode(),
                headers={'Content-Type': 'application/json'})
            with opener.open(request, timeout=2) as response:
                assert response.status in (200, 201)
        return object()

    monkeypatch.setitem(sys.modules, 'webview.platforms.cocoa', types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(
        create_window=create_window, start=lambda **kwargs: None))
    directory = tmp_path / 'first-install'
    desktop().launch(directory)
    token = (directory / 'agent.token').read_text()
    desktop().launch(directory)
    assert (directory / 'agent.token').read_text() == token
    desktop().launch(tmp_path / 'independent-install')
    assert observations == [0, 1, 0]
