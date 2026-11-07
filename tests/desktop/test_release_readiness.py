"""Publication trust gates use real files; no signing key access is needed."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def release_tool():
    spec = importlib.util.spec_from_file_location('release_readiness_tool', ROOT / 'tools/prepare_release.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publication_rejects_missing_bundled_compliance_report(tmp_path):
    app = tmp_path / 'Synthetic.app'
    app.mkdir()
    tool = release_tool()
    with pytest.raises(ValueError, match='compliance'):
        tool.inspect_publication_readiness(app)


@pytest.mark.parametrize('report', [
    {'release_ready': False, 'blockers': []},
    {'release_ready': True, 'blockers': [{'id': 'unresolved'}]},
    {'release_ready': True},
    {'release_ready': 1, 'blockers': []},
])
def test_publication_rejects_uncleared_bundled_compliance(tmp_path, report):
    app = tmp_path / 'Synthetic.app'
    notices = app / 'Contents/Resources/ThirdPartyNotices'
    notices.mkdir(parents=True)
    (notices / 'manifest.json').write_text(json.dumps(report))
    tool = release_tool()
    with pytest.raises(ValueError, match='compliance'):
        tool.inspect_publication_readiness(app)


def test_publication_rejects_real_adhoc_macho_even_with_clearance_claim(tmp_path):
    import plistlib
    import subprocess
    import sys
    if sys.platform != 'darwin':
        pytest.skip('real macOS code signing inspection')
    app = tmp_path / 'Synthetic.app'
    executable = app / 'Contents/MacOS/Synthetic'
    executable.parent.mkdir(parents=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleExecutable': 'Synthetic', 'CFBundleIdentifier': 'test.synthetic.readiness',
        'CFBundlePackageType': 'APPL'}))
    subprocess.run(['/usr/bin/cc', '-x', 'c', '-', '-o', str(executable)],
                   input=b'int main(void) { return 0; }\n', check=True)
    notices = app / 'Contents/Resources/ThirdPartyNotices'
    notices.mkdir(parents=True)
    (notices / 'manifest.json').write_text(json.dumps({'release_ready': True, 'blockers': []}))
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(app)],
                   check=True, capture_output=True)
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)],
                   check=True, capture_output=True)
    tool = release_tool()
    with pytest.raises(ValueError, match='Developer ID'):
        tool.inspect_publication_readiness(app)


def test_dmg_checks_publication_before_returning_and_always_detaches(tmp_path, monkeypatch):
    import subprocess
    tool = release_tool()
    mount = tmp_path / 'mount.noindex'
    mount.mkdir()
    (mount / 'Knowledge Hub.app').mkdir()
    events = []
    def run(command, **kwargs):
        events.append(command[1])
        return subprocess.CompletedProcess(command, 0)
    def inspect(*args):
        events.append('bundle')
    def reject(*args):
        events.append('publication')
        raise ValueError('publication blocked')
    monkeypatch.setattr(tool.subprocess, 'run', run)
    monkeypatch.setattr(tool, 'inspect_bundle', inspect)
    monkeypatch.setattr(tool, 'inspect_publication_readiness', reject)
    with pytest.raises(ValueError, match='publication blocked'):
        tool.inspect_dmg(tmp_path / 'synthetic.dmg', mount, '1.2.3', '12.0.0')
    assert events == ['verify', 'attach', 'bundle', 'publication', 'detach']


def test_real_synthetic_dmg_is_rejected_without_keychain_use(tmp_path):
    import plistlib
    import subprocess
    import sys
    if sys.platform != 'darwin':
        pytest.skip('real macOS packaging tools')
    tool = release_tool()
    image = tmp_path / 'image.noindex'
    app = image / 'Knowledge Hub.app'
    binary = app / 'Contents/MacOS/Knowledge Hub'
    binary.parent.mkdir(parents=True)
    subprocess.run(['/usr/bin/cc', '-arch', 'arm64', '-x', 'c', '-', '-o', str(binary)],
                   input=b'int main(void) { return 0; }\n', check=True)
    (app / 'Contents/Frameworks/Sparkle.framework').mkdir(parents=True)
    info = {'CFBundleVersion': '1.2.3', 'CFBundleShortVersionString': '1.2.3',
            'CFBundleIdentifier': 'com.knowledgehub.desktop', 'CFBundleExecutable': 'Knowledge Hub',
            'LSMinimumSystemVersion': '12.0.0', 'SUFeedURL': tool.FEED_URL,
            'SUPublicEDKey': tool.PUBLIC_KEY, 'SURequireSignedFeed': True,
            'SUSignedFeedFailureExpirationInterval': 0, 'SUVerifyUpdateBeforeExtraction': True,
            'SUEnableAutomaticChecks': False, 'SUAutomaticallyUpdate': False,
            'SUAllowsAutomaticUpdates': False, 'SUEnableSystemProfiling': False}
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    notices = app / 'Contents/Resources/ThirdPartyNotices'
    notices.mkdir(parents=True)
    (notices / 'manifest.json').write_text(json.dumps({
        'release_ready': False, 'blockers': [{'id': 'synthetic-unresolved'}]}))
    dmg = tmp_path / 'synthetic-not-publishable.dmg'
    subprocess.run(['/usr/bin/hdiutil', 'create', '-quiet', '-srcfolder', str(image),
                    '-format', 'UDZO', str(dmg)], check=True)
    mount = tmp_path / 'synthetic-mounted.noindex'
    with pytest.raises(ValueError, match='compliance review is unresolved'):
        tool.inspect_dmg(dmg, mount, '1.2.3', '12.0.0')
    assert not (mount / 'Knowledge Hub.app').exists(), 'owned synthetic DMG remained mounted'

