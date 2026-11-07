"""The only mocked boundary is the OS sheet and main-thread dispatcher."""
import threading
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

from knowledge_hub.context_sources import ContextSources


class SyntheticNative:
    def __init__(self, selection=()):
        self.selection = selection
        self.pending = []
        self.cancelled = False
        self.trusted = True

    def call_after(self, callback):
        callback()

    def install_guard(self, window, trusted_url):
        self.window = window
        self.trusted_url = trusted_url
        return True

    def is_trusted(self, window, trusted_url):
        return self.trusted

    def begin(self, window, complete):
        self.pending.append(complete)
        if self.selection is not None:
            complete(self.selection)

    def cancel(self):
        self.cancelled = True


def test_bridge_registers_mixed_selection_without_paths_or_enumeration(tmp_path, monkeypatch):
    from knowledge_hub.native_picker import DesktopAPI
    folder = tmp_path / 'selected'
    folder.mkdir()
    file = tmp_path / 'note.txt'
    file.write_text('synthetic')
    native = SyntheticNative([folder, file])
    sources = ContextSources(tmp_path / 'data')
    api = DesktopAPI(sources, 'http://127.0.0.1:1234/', adapter=native)
    api._bind(SimpleNamespace())
    api._prepare()
    monkeypatch.setattr(sources, 'list', lambda *_: (_ for _ in ()).throw(AssertionError('no enumeration')))
    with ThreadPoolExecutor() as pool:
        result = pool.submit(api.choose_context_sources).result(2)
    assert result['cancelled'] is False
    assert {source['kind'] for source in result['sources']} == {'file', 'directory'}
    assert str(tmp_path) not in str(result)
    assert len(sources.sources()) == 2


def test_bridge_fail_closed_untrusted_main_thread_and_no_path_argument(tmp_path):
    from knowledge_hub.native_picker import DesktopAPI
    import pytest
    native = SyntheticNative([])
    sources = ContextSources(tmp_path / 'data')
    api = DesktopAPI(sources, 'http://127.0.0.1:1234/', adapter=native)
    assert api.choose_context_sources()['error'] == 'native_picker_unavailable'
    api._bind(SimpleNamespace())
    api._prepare()
    assert api.choose_context_sources()['error'] == 'native_picker_main_thread'
    native.trusted = False
    with ThreadPoolExecutor() as pool:
        assert pool.submit(api.choose_context_sources).result(2)['error'] == 'untrusted_desktop_page'
    with pytest.raises(TypeError):
        api.choose_context_sources('/etc')
    assert sources.sources() == []


def test_bridge_concurrent_close_and_timeout_cannot_grant(tmp_path):
    from knowledge_hub.native_picker import DesktopAPI
    native = SyntheticNative(None)
    sources = ContextSources(tmp_path / 'data')
    api = DesktopAPI(sources, 'http://127.0.0.1:1234/', adapter=native, timeout=0.1)
    api._bind(SimpleNamespace())
    api._prepare()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(api.choose_context_sources)
        while not native.pending:
            threading.Event().wait(0.001)
        assert pool.submit(api.choose_context_sources).result(2)['error'] == 'native_picker_busy'
        api._close()
        assert first.result(2)['cancelled']
    file = tmp_path / 'late.txt'
    file.write_text('not a grant')
    native.pending[0]([file])
    assert sources.sources() == []
    assert native.cancelled
    other_native = SyntheticNative(None)
    other = DesktopAPI(sources, 'http://127.0.0.1:1234/', adapter=other_native, timeout=0.01)
    other._bind(SimpleNamespace())
    other._prepare()
    with ThreadPoolExecutor() as pool:
        assert pool.submit(other.choose_context_sources).result(2)['error'] == 'native_picker_timeout'
    assert other_native.cancelled


def test_trusted_page_is_exact_loopback_origin_and_root():
    from knowledge_hub.native_picker import trusted_page
    base = 'http://127.0.0.1:1234/'
    assert trusted_page(base + '#token=synthetic', base)
    for url in ['https://example.com/', 'http://127.0.0.1:1235/', base + 'api/health', base + '?html=x', 'file:///tmp/x', 'http://localhost:1234/']:
        assert not trusted_page(url, base)


def test_desktop_passes_only_bridge_and_hooks_guard_before_load(tmp_path, monkeypatch):
    import sys
    import types
    import knowledge_hub.desktop as desktop
    from webview.event import Event
    captured = {}
    def create_window(title, url, **kwargs):
        captured['api'] = kwargs.get('js_api')
        window = SimpleNamespace(uid='synthetic', native=object())
        window.events = SimpleNamespace(before_show=Event(window, True), closed=Event(window, True))
        captured['window'] = window
        return window
    def start(**kwargs):
        assert captured['api'] is None  # No dynamic pywebview API is exposed.
        captured['api'] = captured['window'].events.before_show._items[0].__self__
        assert captured['api']._window is captured['window']
        assert len(captured['window'].events.before_show) == 1
        assert len(captured['window'].events.closed) == 1
        captured['window'].events.closed.set()
    monkeypatch.setitem(sys.modules, 'webview.platforms.cocoa', types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'webview', types.SimpleNamespace(create_window=create_window, start=start))
    from knowledge_hub.native_picker import CocoaPicker
    monkeypatch.setattr(CocoaPicker, 'call_after', staticmethod(lambda fn: fn()))
    desktop.launch(tmp_path / 'data')
    assert captured['api']._closed.is_set()


def test_real_cocoa_startup_bridge_under_strict_csp(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    import pytest
    if sys.platform != 'darwin' or os.environ.get('KNOWLEDGE_HUB_NATIVE_PICKER_QA') != '1':
        pytest.skip('opt-in real Cocoa initial startup/bridge acceptance')
    script = Path(__file__).parent / 'desktop' / 'native_bridge_probe.py'
    result = subprocess.run([sys.executable, str(script), str(tmp_path / 'startup')],
                            capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_cocoa_sheet_synthetic_cancellation(tmp_path):
    """Opt-in real AppKit cancellation; synthetic selection is tested above."""
    import os
    import subprocess
    import sys
    import pytest
    if sys.platform != 'darwin' or os.environ.get('KNOWLEDGE_HUB_NATIVE_PICKER_QA') != '1':
        pytest.skip('opt-in AppKit synthetic panel acceptance')
    script = r'''
import json, sys, threading
from pathlib import Path
from types import SimpleNamespace
import AppKit, Foundation
from PyObjCTools import AppHelper
from knowledge_hub.native_picker import CocoaPicker
root = Path(sys.argv[1])
root.mkdir()
file = root / 'synthetic-evidence.txt'
file.write_text('native synthetic evidence')
app = AppKit.NSApplication.sharedApplication()
app.setActivationPolicy_(1)
window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
    AppKit.NSMakeRect(100, 100, 600, 400), AppKit.NSWindowStyleMaskTitled, AppKit.NSBackingStoreBuffered, False)
window.setReleasedWhenClosed_(False)
window.setTitle_('Knowledge Hub synthetic native picker QA')
window.makeKeyAndOrderFront_(None)
panel = AppKit.NSOpenPanel.openPanel()
panel.setDirectoryURL_(Foundation.NSURL.fileURLWithPath_(str(root)))
panel.setNameFieldStringValue_(file.name)
# Preserve the real panel and native API; replace only the factory so production
# cannot initially navigate to an owner's last-used directory during this probe.
original_module = sys.modules['AppKit']
class Factory:
    @staticmethod
    def openPanel(): return panel
class Proxy:
    NSOpenPanel = Factory
    def __getattr__(self, key): return getattr(original_module, key)
sys.modules['AppKit'] = Proxy()
picker = CocoaPicker()
import WebKit
from webview.platforms.cocoa import BrowserView
view = WebKit.WKWebView.alloc().initWithFrame_configuration_(AppKit.NSMakeRect(0, 0, 600, 400), WebKit.WKWebViewConfiguration.alloc().init())
BrowserView.instances['synthetic-qa'] = SimpleNamespace(window=window, webview=view)
assert picker.install_guard(SimpleNamespace(uid='synthetic-qa', native=window), 'http://127.0.0.1:1234/')
result = {'guard_installed': True}
def complete(paths):
    result['paths'] = [str(path) for path in paths]
    result['mixed'] = bool(panel.canChooseFiles() and panel.canChooseDirectories() and panel.allowsMultipleSelection())
    result['packages_opaque'] = not panel.treatsFilePackagesAsDirectories()
    (root / 'result.json').write_text(json.dumps(result))
    AppHelper.stopEventLoop()
def start():
    picker.begin(SimpleNamespace(native=window), complete)
    def confirm():
        picker.cancel()
    AppHelper.callLater(0.5, confirm)
def timeout():
    result['timeout'] = True
    picker.cancel()
    AppHelper.stopEventLoop()
AppHelper.callAfter(start)
AppHelper.callLater(8, timeout)
AppHelper.runEventLoop()
window.orderOut_(None)
assert result.get('paths') == [] and not result.get('timeout'), result
assert result['mixed'] and result['packages_opaque'], result
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path / 'panel-fixture')], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    import json
    observed = json.loads((tmp_path / 'panel-fixture/result.json').read_text())
    assert observed['paths'] == [] and not observed.get('timeout')
    assert observed['mixed'] and observed['packages_opaque'] and observed['guard_installed']
