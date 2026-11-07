"""Synthetic native boundaries; these tests never contact a release feed."""
import importlib
import os
import plistlib
import pytest
from pathlib import Path


FEED = 'https://github.com/NewBww/knowledge-hub/releases/latest/download/appcast.xml'
KEY = 'eRN7w0nSTjTGD/AIwzhAYCE7Ltgm+3yqxlWK1CP11fQ='
POLICY = {
    'CFBundleIdentifier': 'com.knowledgehub.desktop',
    'SUFeedURL': FEED, 'SUPublicEDKey': KEY,
    'SUEnableAutomaticChecks': False, 'SUAutomaticallyUpdate': False,
    'SUAllowsAutomaticUpdates': False, 'SUEnableSystemProfiling': False,
    'SUVerifyUpdateBeforeExtraction': True, 'SURequireSignedFeed': True,
    'SUSignedFeedFailureExpirationInterval': 0,
    'LSMinimumSystemVersion': '12.0.0',
}


def bundle(tmp_path):
    app = tmp_path / 'Synthetic.app'
    executable = app / 'Contents/MacOS/Synthetic'
    executable.parent.mkdir(parents=True)
    executable.write_text('synthetic')
    (app / 'Contents/Frameworks/Sparkle.framework').mkdir(parents=True)
    return app, executable


def test_frozen_bundle_accepts_only_fixed_public_trust_metadata(tmp_path):
    module = native()
    app, executable = bundle(tmp_path)
    assert module.validate_bundle(app, POLICY, executable) == app / 'Contents/Frameworks/Sparkle.framework'
    for key, changed in [('SUFeedURL', 'https://attacker.invalid/feed'),
                         ('SUPublicEDKey', 'untrusted'), ('SURequireSignedFeed', False),
                         ('SUVerifyUpdateBeforeExtraction', False),
                         ('SUSignedFeedFailureExpirationInterval', 20),
                         ('SUEnableAutomaticChecks', True), ('SUAutomaticallyUpdate', True),
                         ('SUAllowsAutomaticUpdates', True), ('SUEnableSystemProfiling', True),
                         ('CFBundleIdentifier', 'com.other.app'),
                         ('LSMinimumSystemVersion', '11.0')]:
        with pytest.raises(RuntimeError, match='bundle policy'):
            module.validate_bundle(app, {**POLICY, key: changed}, executable)


def test_bundle_rejects_nonbundle_readonly_mount_and_external_framework(tmp_path, monkeypatch):
    module = native()
    app, executable = bundle(tmp_path)
    with pytest.raises(RuntimeError, match='executable'):
        module.validate_bundle(app, POLICY, tmp_path / 'other')
    framework = app / 'Contents/Frameworks/Sparkle.framework'
    framework.rmdir()
    framework.symlink_to(tmp_path)
    with pytest.raises(RuntimeError, match='framework'):
        module.validate_bundle(app, POLICY, executable)
    framework.unlink()
    framework.mkdir()
    monkeypatch.setattr(module.os, 'statvfs', lambda _: type('Stat', (), {'f_flag': os.ST_RDONLY})())
    with pytest.raises(RuntimeError, match='read-only'):
        module.validate_bundle(app, POLICY, executable)


class Controller:
    def __init__(self):
        self.checks = 0
        self.active = False
        self.can_check = True

    def updater(self):
        return self

    def canCheckForUpdates(self):
        return self.can_check

    def sessionInProgress(self):
        return self.active

    def checkForUpdates_(self, sender):
        self.checks += 1
        self.active = True


def test_checks_dispatch_to_main_and_repeated_native_session_is_rejected():
    import threading
    module = native()
    controller, queue, errors = Controller(), [], []
    bridge = module.NativeUpdater(controller, object(), queue.append,
                                  lambda: threading.current_thread() is threading.main_thread(), timeout=1)

    def check():
        try:
            bridge.check_for_updates()
        except RuntimeError as error:
            errors.append(str(error))

    worker = threading.Thread(target=check)
    worker.start()
    import time
    deadline = time.monotonic() + 1
    while not queue and time.monotonic() < deadline:
        time.sleep(0.001)
    assert controller.checks == 0
    # Supplemental coverage: concurrent HTTP requests cannot queue another check.
    with pytest.raises(RuntimeError, match='already active'):
        bridge.check_for_updates()
    queue.pop()()
    worker.join(1)
    assert errors == []
    assert controller.checks == 1
    with pytest.raises(RuntimeError, match='already active'):
        bridge.check_for_updates()
    assert controller.checks == 1
    controller.active = False
    controller.can_check = False
    with pytest.raises(RuntimeError, match='not ready'):
        bridge.check_for_updates()


def test_timed_out_main_dispatch_never_opens_late_native_dialog():
    module = native()
    controller, queue = Controller(), []
    bridge = module.NativeUpdater(controller, object(), queue.append, lambda: False, timeout=0.01)
    with pytest.raises(RuntimeError, match='timed out'):
        bridge.check_for_updates()
    queue.pop()()
    assert controller.checks == 0


def test_runtime_preferences_override_persisted_automatic_settings_before_start():
    module = native()

    class Startup(Controller):
        def __init__(self):
            super().__init__()
            self.values = [True, True, True]
            self.started = False

        def setAutomaticallyChecksForUpdates_(self, value):
            self.values[0] = value

        def setAutomaticallyDownloadsUpdates_(self, value):
            self.values[1] = value

        def setSendsSystemProfile_(self, value):
            self.values[2] = value

        def startUpdater_(self, error):
            assert self.values == [False, False, False]
            self.started = True
            return True

        def automaticallyChecksForUpdates(self):
            return self.values[0]

        def automaticallyDownloadsUpdates(self):
            return self.values[1]

        def sendsSystemProfile(self):
            return self.values[2]

    controller = Startup()
    module.configure_controller(controller)
    assert controller.started
    assert controller.values == [False, False, False]
    assert controller.checks == 0
    controller.startUpdater_ = lambda _: False
    with pytest.raises(RuntimeError, match='Sparkle could not start'):
        module.configure_controller(controller)


def test_frozen_initialization_waits_for_main_runloop_and_reports_failure(tmp_path, monkeypatch):
    import types
    import sys
    module = native()
    app, executable = bundle(tmp_path)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(POLICY))
    monkeypatch.setattr(module.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(module.sys, 'executable', str(executable))
    queue, ready, unavailable = [], [], []
    bundle_class = types.SimpleNamespace(mainBundle=lambda: types.SimpleNamespace(bundlePath=lambda: str(app)))
    monkeypatch.setitem(sys.modules, 'Foundation', types.SimpleNamespace(
        NSBundle=bundle_class, NSThread=types.SimpleNamespace(isMainThread=lambda: True)))
    monkeypatch.setitem(sys.modules, 'PyObjCTools', types.SimpleNamespace(
        AppHelper=types.SimpleNamespace(callAfter=queue.append)))
    controller, delegate = Controller(), object()
    monkeypatch.setattr(module, 'create_controller', lambda path: (controller, delegate))
    module.initialize_native_updater(ready.append, unavailable.append)
    assert not ready and not unavailable
    queue.pop()()
    assert ready[0].controller is controller and ready[0].delegate is delegate
    assert controller.checks == 0
    assert unavailable == []
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({**POLICY, 'SURequireSignedFeed': False}))
    module.initialize_native_updater(ready.append, unavailable.append)
    queue.pop()()
    assert 'bundle policy' in unavailable[0]
    assert len(ready) == 1


def test_controller_uses_validated_sparkle_api_and_delegate_blocks_preferences(monkeypatch, tmp_path):
    import types
    import sys
    module = native()
    seen = []

    class NSObject:
        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            return self

    class Standard(NSObject):
        def initWithStartingUpdater_updaterDelegate_userDriverDelegate_(self, start, delegate, driver):
            seen.append((start, delegate, driver))
            return self

    signatures = []
    monkeypatch.setitem(sys.modules, 'objc', types.SimpleNamespace(
        loadBundle=lambda name, namespace, bundle_path: seen.append((name, bundle_path)),
        lookUpClass=lambda name: Standard,
        signature=lambda signature: (signatures.append(signature) or (lambda fn: fn))))
    monkeypatch.setitem(sys.modules, 'Foundation', types.SimpleNamespace(
        NSObject=NSObject, NSSet=types.SimpleNamespace(set=lambda: frozenset())))
    monkeypatch.setattr(module, 'configure_controller', lambda controller: seen.append(controller))
    framework = tmp_path / 'Sparkle.framework'
    controller, delegate = module.create_controller(framework)
    assert seen[0] == ('Sparkle', str(framework))
    assert seen[1] == (False, delegate, None)
    assert seen[2] is controller
    assert delegate.feedURLStringForUpdater_(controller) == FEED
    assert delegate.allowedChannelsForUpdater_(controller) == frozenset()
    assert delegate.allowedSystemProfileKeysForUpdater_(controller) == []
    assert delegate.feedParametersForUpdater_sendingSystemProfile_(controller, True) == []
    assert delegate.updaterShouldPromptForPermissionToCheckForUpdates_(controller) is False
    assert b'@@:@B' in signatures  # BOOL argument must not be inferred as an object.


def native():
    return importlib.import_module('knowledge_hub.native_updater')


def test_source_runtime_reports_unsupported_without_loading_cocoa(monkeypatch):
    module = native()
    monkeypatch.delattr(module.sys, 'frozen', raising=False)
    ready, unavailable = [], []
    module.initialize_native_updater(ready.append, unavailable.append)
    assert ready == []
    assert unavailable == ['Native updates require the frozen macOS application bundle']
