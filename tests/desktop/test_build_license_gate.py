"""Local previews retain notices without bypassing public-release compliance gates."""
import importlib.util
import json
import platform
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def synthetic_arm64_host(monkeypatch):
    """Reach mocked orchestration, not a real native build on the test host."""
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(platform, 'machine', lambda: 'arm64')


def builder():
    spec = importlib.util.spec_from_file_location('notice_builder', ROOT / 'tools/build_macos.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_build_stops_on_unresolved_license_prerequisites(tmp_path):
    sdk = tmp_path / 'sdk'
    sdk.mkdir()
    (sdk / 'LICENSE').write_text('Synthetic SDK license')
    app = tmp_path / 'Synthetic.app'
    app.mkdir()

    def collect(bundle, destination, **kwargs):
        destination.mkdir(parents=True)
        return {'blockers': [{'id': 'synthetic-unresolved'}], 'release_ready': False}

    with pytest.raises(RuntimeError, match='publication blocked'):
        builder().collect_bundle_notices(app, sdk, tmp_path / 'Analysis.toc', collector=collect)


def test_local_preview_preserves_sdk_license_and_blocked_manifest(tmp_path):
    sdk = tmp_path / 'sdk'
    sdk.mkdir()
    license_bytes = b'Synthetic complete SDK license\n'
    (sdk / 'LICENSE').write_bytes(license_bytes)
    app = tmp_path / 'Synthetic.app'
    app.mkdir()
    toc = tmp_path / 'Analysis.toc'

    def collect(bundle, destination, **kwargs):
        assert bundle == app
        assert kwargs['analysis_toc'] == toc
        destination.mkdir(parents=True)
        return {'blockers': [{'id': 'synthetic-unresolved'}], 'release_ready': False}

    report = builder().collect_bundle_notices(app, sdk, toc, collector=collect, local_preview=True)
    destination = app / 'Contents/Resources/ThirdPartyNotices'
    assert (destination / 'Sparkle-LICENSE.txt').read_bytes() == license_bytes
    manifest = json.loads((destination / 'manifest.json').read_text())
    assert manifest == report
    assert manifest['release_ready'] is False
    assert manifest['blockers'] == [{'id': 'synthetic-unresolved'}]
    assert manifest['frameworks'][0]['name'] == 'Sparkle'
    assert str(tmp_path) not in json.dumps(manifest)


def test_build_collects_notices_before_signing_and_stops_public_output(tmp_path, monkeypatch, synthetic_arm64_host):
    import plistlib
    module = builder()
    app = tmp_path / 'Synthetic.app'
    (app / 'Contents').mkdir(parents=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({}))
    calls = []
    metadata = {'version': '1.2.3', 'artifact': 'Synthetic.dmg'}
    monkeypatch.setattr(module, 'validate_sparkle_distribution', lambda path: path)
    monkeypatch.setattr(module, 'prepare_build', lambda root, out, work: {
        'app': app, 'stage': tmp_path, 'pyinstaller': ['synthetic-freezer'],
        'image_stage': tmp_path / 'image', 'image': tmp_path / 'Synthetic.dmg',
        'metadata': metadata, 'dmg': ['synthetic-image']})
    monkeypatch.setattr(module, 'bundle_plist', lambda metadata: {})
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'embed_sparkle', lambda *args: calls.append('embed'))
    monkeypatch.setattr(module, 'sign_app', lambda *args: calls.append('sign'))
    monkeypatch.setattr(module, 'stage_image', lambda *args: None)

    def blocked(*args, **kwargs):
        calls.append('notices')
        raise RuntimeError('Binary publication blocked')

    monkeypatch.setattr(module, 'collect_bundle_notices', blocked)
    with pytest.raises(RuntimeError, match='publication blocked'):
        module.main(['--out', str(tmp_path), '--sparkle-distribution', str(tmp_path / 'sdk')])
    assert calls == ['embed', 'notices']


def test_missing_sdk_license_fails_even_for_local_preview(tmp_path):
    app = tmp_path / 'Synthetic.app'
    app.mkdir()
    with pytest.raises(RuntimeError, match='SDK license'):
        builder().collect_bundle_notices(app, tmp_path / 'sdk', tmp_path / 'Analysis.toc', local_preview=True)
