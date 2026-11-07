"""Manual-only Sparkle bridge. Trust comes only from the frozen application's bundle."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path


FEED_URL = 'https://github.com/NewBww/knowledge-hub/releases/latest/download/appcast.xml'
PUBLIC_KEY = 'eRN7w0nSTjTGD/AIwzhAYCE7Ltgm+3yqxlWK1CP11fQ='
BUNDLE_POLICY = {
    'CFBundleIdentifier': 'com.knowledgehub.desktop',
    'SUFeedURL': FEED_URL, 'SUPublicEDKey': PUBLIC_KEY,
    'SUEnableAutomaticChecks': False, 'SUAutomaticallyUpdate': False,
    'SUAllowsAutomaticUpdates': False, 'SUEnableSystemProfiling': False,
    'SUVerifyUpdateBeforeExtraction': True, 'SURequireSignedFeed': True,
    'SUSignedFeedFailureExpirationInterval': 0,
    'LSMinimumSystemVersion': '12.0.0',
}


def validate_bundle(app: Path, info: dict, executable: Path) -> Path:
    """Reject non-app, overridden trust policy and non-updatable bundle locations."""
    app = app.resolve()
    executable = executable.resolve()
    if app.suffix != '.app' or executable.parent != app / 'Contents/MacOS':
        raise RuntimeError('Native updates require the frozen bundle executable')
    for key, expected in BUNDLE_POLICY.items():
        if type(info.get(key)) is not type(expected) or info[key] != expected:
            raise RuntimeError(f'Native update bundle policy is invalid: {key}')
    framework = app / 'Contents/Frameworks/Sparkle.framework'
    if not framework.is_dir() or not framework.resolve().is_relative_to(app):
        raise RuntimeError('Native update framework is missing or outside the application')
    if os.statvfs(app).f_flag & os.ST_RDONLY or not os.access(app, os.W_OK):
        raise RuntimeError('Native updates are unavailable on a read-only application; copy it to a writable volume first')
    return framework


class NativeUpdater:
    """Retain Sparkle's weak delegate and serialize manual Cocoa checks."""

    def __init__(self, controller, delegate, dispatch, on_main, timeout=5):
        self.controller = controller
        self.delegate = delegate
        self.dispatch = dispatch
        self.on_main = on_main
        self.timeout = timeout
        self._checking = threading.Lock()

    def check_for_updates(self) -> None:
        if not self._checking.acquire(blocking=False):
            raise RuntimeError('A native update check is already active')
        done = threading.Event()
        gate = threading.Lock()
        cancelled = False
        errors = []

        def check():
            with gate:
                if cancelled:
                    return
                try:
                    if not self.on_main():
                        raise RuntimeError('Native update dispatch did not reach the main thread')
                    updater = self.controller.updater()
                    if updater.sessionInProgress():
                        raise RuntimeError('A native update session is already active')
                    if not updater.canCheckForUpdates():
                        raise RuntimeError('The native updater is not ready')
                    self.controller.checkForUpdates_(None)
                except Exception as error:
                    errors.append(error)
                finally:
                    done.set()

        try:
            if self.on_main():
                check()
            else:
                self.dispatch(check)
            if not done.wait(self.timeout):
                with gate:
                    cancelled = True
                raise RuntimeError('Native update main-thread dispatch timed out; no queued check will run')
            if errors:
                raise RuntimeError(str(errors[0])) from None
        finally:
            self._checking.release()


def configure_controller(controller) -> None:
    """Disable saved scheduling/download/profile choices before the next runloop."""
    updater = controller.updater()
    updater.setAutomaticallyChecksForUpdates_(False)
    updater.setAutomaticallyDownloadsUpdates_(False)
    updater.setSendsSystemProfile_(False)
    # loadBundle does not register NSError out metadata: the proven result is BOOL.
    if not updater.startUpdater_(None):
        raise RuntimeError('Sparkle could not start; verify the signed bundle configuration')
    updater.setAutomaticallyChecksForUpdates_(False)
    updater.setAutomaticallyDownloadsUpdates_(False)
    updater.setSendsSystemProfile_(False)
    if (updater.automaticallyChecksForUpdates() or updater.automaticallyDownloadsUpdates()
            or updater.sendsSystemProfile()):
        raise RuntimeError('Sparkle manual-only privacy policy could not be applied')


def create_controller(framework: Path):
    import objc
    from Foundation import NSObject, NSSet

    objc.loadBundle('Sparkle', globals(), bundle_path=str(framework))

    class KnowledgeHubSparkleDelegate(NSObject):
        def feedURLStringForUpdater_(self, updater):
            return FEED_URL

        def allowedChannelsForUpdater_(self, updater):
            return NSSet.set()

        def allowedSystemProfileKeysForUpdater_(self, updater):
            return []

        @objc.signature(b'@@:@B')
        def feedParametersForUpdater_sendingSystemProfile_(self, updater, sending):
            return []

        @objc.signature(b'B@:@')
        def updaterShouldPromptForPermissionToCheckForUpdates_(self, updater):
            return False

    delegate = KnowledgeHubSparkleDelegate.alloc().init()
    controller = objc.lookUpClass('SPUStandardUpdaterController').alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(
        False, delegate, None)
    if controller is None:
        raise RuntimeError('Sparkle native controller could not be created')
    configure_controller(controller)
    return controller, delegate


def initialize_native_updater(on_ready, on_unavailable) -> None:
    """Called by pywebview's startup worker, never by the headless/MCP entrypoint."""
    if sys.platform != 'darwin' or not getattr(sys, 'frozen', False):
        on_unavailable('Native updates require the frozen macOS application bundle')
        return
    try:
        from Foundation import NSBundle, NSThread
        from PyObjCTools import AppHelper
    except ImportError:
        on_unavailable('Native updates require the Cocoa Sparkle runtime')
        return

    def start():
        try:
            if not NSThread.isMainThread():
                raise RuntimeError('Native updater startup did not reach the main thread')
            import plistlib
            app = Path(NSBundle.mainBundle().bundlePath())
            with (app / 'Contents/Info.plist').open('rb') as stream:
                info = plistlib.load(stream)
            framework = validate_bundle(app, info, Path(sys.executable))
            controller, delegate = create_controller(framework)
            on_ready(NativeUpdater(controller, delegate, AppHelper.callAfter, NSThread.isMainThread))
        except Exception as error:
            on_unavailable(f'Native updater unavailable: {error}')

    try:
        AppHelper.callAfter(start)
    except Exception:
        on_unavailable('Native updater could not schedule Cocoa startup')
