"""macOS mixed native sheet. Only a trusted local page can invoke this bridge.

This is ordinary user-consented filesystem access, not an App Sandbox entitlement
or security-scoped-bookmark implementation. Permissions are revalidated on reads.
"""
from __future__ import annotations

from pathlib import Path
import threading
from urllib.parse import urlsplit

from .core import DomainError


def trusted_page(url, base):
    try:
        candidate, expected = urlsplit(str(url)), urlsplit(base)
        return (expected.scheme == 'http' and expected.hostname == '127.0.0.1'
                and candidate.scheme == expected.scheme and candidate.netloc == expected.netloc
                and candidate.path == '/' and not candidate.query
                and not candidate.username and not candidate.password)
    except (ValueError, TypeError):
        return False


_GUARD_CLASS = None


class CocoaPicker:
    def __init__(self):
        self.panel = None
        self.view = None
        self.guard = None

    @staticmethod
    def call_after(callback):
        from PyObjCTools import AppHelper
        AppHelper.callAfter(callback)

    def install_guard(self, window, trusted_url):
        # pywebview Cocoa publishes Window.native as NSWindow, not BrowserView.
        from webview.platforms.cocoa import BrowserView
        instance = BrowserView.instances.get(window.uid)
        if instance is None or instance.window is not window.native:
            return False
        self.view = instance.webview
        global _GUARD_CLASS
        if _GUARD_CLASS is None:
            class KnowledgeHubNavigationGuard(BrowserView.BrowserDelegate):
                def webView_decidePolicyForNavigationAction_decisionHandler_(self, view, action, handler):
                    url = action.request().URL().absoluteString()
                    frame = action.targetFrame()
                    handler(1 if frame is not None and frame.isMainFrame() and trusted_page(url, self.trusted_url) else 0)

                def webView_didFinishNavigation_(self, view, navigation):
                    # Do not call pywebview's injector: its dynamic API uses
                    # new Function/eval, forbidden by the application's CSP.
                    instance = BrowserView.get_instance('webview', view)
                    if instance and trusted_page(view.URL().absoluteString(), self.trusted_url):
                        if not view.window():
                            instance.window.setContentView_(view)
                            instance.window.makeFirstResponder_(view)
                        instance.pywebview_window.events.loaded.set()

                def userContentController_didReceiveScriptMessage_replyHandler_(self, controller, message, reply):
                    import Foundation
                    api = self.picker_api
                    frame = message.frameInfo()
                    if (message.webView() != api._adapter.view or not frame.isMainFrame()
                            or not trusted_page(frame.request().URL().absoluteString(), self.trusted_url)
                            or not api._adapter.is_trusted(api._window, self.trusted_url)):
                        reply({'error': 'untrusted_desktop_page'}, None)
                        return
                    if message.body() is not None and message.body() != Foundation.NSNull.null():
                        reply({'error': 'invalid_native_picker_request'}, None)
                        return

                    def choose():
                        result = api.choose_context_sources()
                        # WebKit replies are structured values, never JS source.
                        api._adapter.call_after(lambda: reply(result, None))
                    threading.Thread(target=choose, name='context-picker', daemon=True).start()

                def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(self, view, config, action, features):
                    # No new native page may inherit the filesystem bridge.
                    return None
            _GUARD_CLASS = KnowledgeHubNavigationGuard
        self.guard = _GUARD_CLASS.alloc().init()
        self.guard.trusted_url = trusted_url
        self.view.setNavigationDelegate_(self.guard)
        self.view.setUIDelegate_(self.guard)
        return True

    def install_bridge(self, api):
        import WebKit
        self.guard.picker_api = api
        controller = self.view.configuration().userContentController()
        # Remove pywebview's general-purpose dispatch/evaluation surfaces.
        controller.removeScriptMessageHandlerForName_('jsBridge')
        controller.removeScriptMessageHandlerForName_('browserDelegate')
        controller.addScriptMessageHandlerWithReply_contentWorld_name_(
            self.guard, WebKit.WKContentWorld.pageWorld(), 'knowledgeHubContext')

    def is_trusted(self, window, trusted_url):
        return (self.view is not None and window.native is not None
                and self.view.navigationDelegate() == self.guard
                and self.view.URL() is not None
                and trusted_page(self.view.URL().absoluteString(), trusted_url))

    def begin(self, window, complete):
        import AppKit
        if self.panel is not None:
            raise RuntimeError('picker busy')
        panel = AppKit.NSOpenPanel.openPanel()
        self.panel = panel
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(True)
        panel.setAllowsMultipleSelection_(True)
        panel.setCanCreateDirectories_(False)
        panel.setResolvesAliases_(False)
        panel.setTreatsFilePackagesAsDirectories_(False)
        panel.setShowsHiddenFiles_(False)
        panel.setTitle_('Choose read-only context sources')
        panel.setMessage_('Selected files and folders become read-only, untrusted context. Hidden, secret, generated and ignored paths remain excluded.')
        panel.setPrompt_('Allow read-only access')

        def finished(response):
            self.panel = None
            if response == AppKit.NSModalResponseOK:
                complete([Path(str(url.path())) for url in panel.URLs() if url.isFileURL()])
            else:
                complete([])

        panel.beginSheetModalForWindow_completionHandler_(window.native, finished)

    def cancel(self):
        if self.panel is not None:
            self.panel.cancel_(None)


class DesktopAPI:
    """The sole public JS API has no path argument and never returns local paths."""
    def __init__(self, sources, trusted_url, *, adapter=None, timeout=120):
        self._sources = sources
        self._trusted_url = trusted_url
        self._adapter = adapter or CocoaPicker()
        self._timeout = min(120, max(0.01, timeout))
        self._window = None
        self._ready = False
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._pending = None

    def _bind(self, window):
        self._window = window

    def _prepare(self):
        try:
            self._ready = bool(self._adapter.install_guard(self._window, self._trusted_url))
            if self._ready and hasattr(self._adapter, 'install_bridge'):
                self._adapter.install_bridge(self)
        except Exception:
            self._ready = False
        # A failed guard leaves bridge unavailable; do not silently downgrade.

    def _close(self):
        self._closed.set()
        if self._pending is not None:
            self._pending.set()
        self._adapter.call_after(self._adapter.cancel)

    def choose_context_sources(self):
        if not self._ready or self._window is None or self._closed.is_set():
            return {'error': 'native_picker_unavailable'}
        if threading.current_thread() is threading.main_thread():
            return {'error': 'native_picker_main_thread'}
        if not self._lock.acquire(blocking=False):
            return {'error': 'native_picker_busy'}
        done = threading.Event()
        expired = threading.Event()
        selection = []
        error = []
        self._pending = done
        try:
            def complete(paths):
                if expired.is_set() or self._closed.is_set():
                    done.set()
                    return
                if not self._adapter.is_trusted(self._window, self._trusted_url):
                    error.append('untrusted_desktop_page')
                else:
                    selection.extend(paths[:64])
                done.set()

            def show():
                if expired.is_set() or self._closed.is_set():
                    done.set()
                    return
                try:
                    if not self._adapter.is_trusted(self._window, self._trusted_url):
                        error.append('untrusted_desktop_page')
                        done.set()
                    else:
                        self._adapter.begin(self._window, complete)
                except Exception:
                    error.append('native_picker_unavailable')
                    done.set()

            self._adapter.call_after(show)
            if not done.wait(self._timeout):
                expired.set()
                self._adapter.call_after(self._adapter.cancel)
                return {'error': 'native_picker_timeout'}
            if self._closed.is_set():
                return {'sources': [], 'cancelled': True}
            if error:
                return {'error': error[0]}
            if not selection:
                return {'sources': [], 'cancelled': True}
            try:
                registered = self._sources.register_selected(selection)
                return {'sources': registered, 'cancelled': False}
            except DomainError as failure:
                return {'error': failure.code}
            except Exception:
                return {'error': 'context_registration_failed'}
        finally:
            expired.set()
            self._pending = None
            self._lock.release()
