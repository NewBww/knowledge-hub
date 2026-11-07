"""Dedicated macOS WebKit shell; knowledge lives outside the application bundle."""
from __future__ import annotations

import fcntl
import importlib
import os
import logging
import secrets
import socket
import threading
import time
import urllib.error
import urllib.request

import uvicorn
from pathlib import Path

from platformdirs import user_data_dir


def resolve_data_dir(data_dir: Path | None = None) -> Path:
    return Path(data_dir or os.environ.get('KNOWLEDGE_HUB_DATA_DIR') or
                user_data_dir('Knowledge Hub', appauthor=False)).expanduser().resolve()


def get_agent_token(data_dir: Path) -> str:
    """Reuse the CLI's agent.token, never bake credentials into the bundle."""
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = data_dir / 'agent.token'
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        os.fchmod(stream.fileno(), 0o600)
        token = stream.read()
        if token and (len(token) < 32 or any(character.isspace() for character in token)):
            raise RuntimeError('Invalid agent token file')
        if not token:
            token = secrets.token_urlsafe(32)
            stream.write(token)
            stream.flush()
            os.fsync(stream.fileno())
    return token


class LocalServer:
    """Own the reserved loopback socket and a joined, non-daemon ASGI thread."""

    def __init__(self, app, timeout: float = 10):
        self.timeout = timeout
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(('127.0.0.1', 0))
        self.address = self.socket.getsockname()
        self.url = f'http://127.0.0.1:{self.address[1]}/'
        self.server = uvicorn.Server(uvicorn.Config(
            app, host='127.0.0.1', port=self.address[1], loop='asyncio',
            http='h11', ws='none', access_log=False, log_config=None,
            log_level='critical', timeout_graceful_shutdown=2,
        ))
        self.error = None
        self.thread = threading.Thread(target=self._run, name='knowledge-hub-http', daemon=False)

    def _run(self):
        try:
            self.server.run(sockets=[self.socket])
        except BaseException as error:
            self.error = error

    def __enter__(self):
        self.thread.start()
        deadline = time.monotonic() + self.timeout
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            while time.monotonic() < deadline:
                if not self.thread.is_alive():
                    raise RuntimeError('Local application server failed to start') from None
                if self.server.started:
                    try:
                        with opener.open(self.url, timeout=0.25) as response:
                            if response.status == 200:
                                return self
                    except (OSError, urllib.error.URLError):
                        pass
                time.sleep(0.02)
            raise RuntimeError('Local application server readiness timed out')
        except BaseException:
            self.close()
            raise

    def close(self):
        self.server.should_exit = True
        if self.thread.ident is not None:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                self.server.force_exit = True
                self.thread.join(timeout=3)
            if self.thread.is_alive():
                raise RuntimeError('Local application server did not stop')
        self.socket.close()

    def __exit__(self, *_):
        self.close()


def launch(data_dir: Path | None = None) -> None:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('The desktop window must run on the main thread')
    try:
        import webview
        # pywebview's selector can otherwise fall back from Cocoa to Qt.
        importlib.import_module('webview.platforms.cocoa')
    except ImportError:
        raise RuntimeError('Native desktop requires pywebview and the macOS desktop extra') from None
    from knowledge_hub.http import create_app

    directory = resolve_data_dir(data_dir)
    human_token = secrets.token_urlsafe(32)
    app = create_app(data_dir=directory, human_token=human_token,
                     agent_token=get_agent_token(directory))
    with LocalServer(app) as server:
        logger = logging.getLogger('pywebview')
        previous_disabled = logger.disabled
        logger.disabled = True  # Native diagnostics may include the bootstrap URL.
        try:
            from .native_picker import DesktopAPI
            api = DesktopAPI(app.state.context_sources, server.url)
            window = webview.create_window(
                'Knowledge Hub', url=f'{server.url}#token={human_token}',
                width=1180, height=800, min_size=(640, 480), text_select=True,
                # Picker uses an app-owned, CSP-safe WebKit reply handler.
                # Never expose pywebview's dynamic general-purpose JS API.
            )
            if window is None:
                raise RuntimeError('Window creation was cancelled')
            api._bind(window)
            if getattr(window, 'events', None) is not None:
                # Cocoa before_show is synchronous and precedes the first load.
                window.events.before_show += api._prepare
                window.events.closed += api._close
            def initialize_updates():
                from knowledge_hub.native_updater import initialize_native_updater

                def ready(native):
                    # Retains both the native controller and its weak delegate.
                    app.state.updater.native = native
                    app.state.updater.unavailable_reason = None

                def unavailable(reason):
                    app.state.updater.native = None
                    app.state.updater.unavailable_reason = reason

                initialize_native_updater(ready, unavailable)

            app.state.updater.unavailable_reason = 'Native updater is starting'
            webview.start(func=initialize_updates, gui='cocoa', debug=False, private_mode=True)
        except Exception:
            raise RuntimeError('Native WebKit window could not start; no browser fallback is used') from None
        finally:
            logger.disabled = previous_disabled
