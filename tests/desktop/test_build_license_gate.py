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
    monkeypatch.setattr(module, 'sanitize_install_metadata', lambda *args: calls.append('sanitize') or [])
    monkeypatch.setattr(module, 'sign_app', lambda *args: calls.append('sign'))
    monkeypatch.setattr(module, 'stage_image', lambda *args: None)

    def blocked(*args, **kwargs):
        calls.append('notices')
        raise RuntimeError('Binary publication blocked')

    monkeypatch.setattr(module, 'collect_bundle_notices', blocked)
    with pytest.raises(RuntimeError, match='publication blocked'):
        module.main(['--out', str(tmp_path), '--sparkle-distribution', str(tmp_path / 'sdk')])
    assert calls == ['embed', 'sanitize', 'notices']


@pytest.mark.parametrize('local_preview', [True, False])
def test_build_indexes_isolated_lxml_metadata_with_shipped_native(tmp_path, monkeypatch,
                                                               synthetic_arm64_host, local_preview):
    """Real installed wheel staged outside installed RECORD ownership; no freeze/sign."""
    import hashlib
    import importlib.metadata as metadata
    import plistlib
    import shutil

    module = builder()
    app = tmp_path / 'Example.app'
    (app / 'Contents').mkdir(parents=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({}))
    sdk = tmp_path / 'sdk'
    sdk.mkdir()
    (sdk / 'LICENSE').write_text('Synthetic SDK license\n')
    installed = metadata.distribution('lxml')
    expected = {}
    native_paths = []
    calls = []

    def prepare(root, out, work):
        candidate = work / 'lxml-candidate'
        candidate.mkdir()
        # Preserve real METADATA/RECORD/license bytes, but relocate their ownership.
        for entry in installed.files or []:
            relative = Path(str(entry))
            if relative.parts[0].endswith('.dist-info') or (
                    relative.parts[0] == 'lxml' and relative.suffix == '.so'):
                source = Path(str(installed.locate_file(entry)))
                target = candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                if relative.name in ('LICENSE', 'LICENSE.txt', 'LICENSES.txt'):
                    expected[relative.as_posix()] = source.read_bytes()
                if relative.suffix == '.so' and relative.name.startswith(('etree.', 'objectify.')):
                    native_paths.append(target)
        assert expected, 'real lxml wheel must supply full license texts'
        assert len(native_paths) == 2
        files = {p.relative_to(candidate).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in candidate.rglob('*') if p.is_file()}
        provenance = {'files': files, 'native': [{'file': p.name} for p in native_paths],
                      'release_ready': False, 'publication_blocked': True}
        records = []
        for source in native_paths:
            records.append(('lxml.' + source.name.split('.')[0], str(source), 'EXTENSION'))
            target = app / 'Contents/Frameworks/lxml' / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        for name, module_name in [('pypdf', 'pypdf'), ('proxy_tools', 'proxy_tools')]:
            source = metadata.distribution(name).locate_file(module_name + '/__init__.py')
            records.append((module_name, str(source), 'PYMODULE'))
        toc = work / 'build/Knowledge Hub/Analysis-00.toc'
        toc.parent.mkdir(parents=True)
        toc.write_text(repr(([], records)))
        out.mkdir(exist_ok=True)
        return {'app': app, 'stage': tmp_path, 'pyinstaller': ['synthetic-freezer'],
                'image_stage': tmp_path / 'image', 'image': out / 'Synthetic.dmg',
                'metadata': {'version': '1.2.3', 'artifact': 'Synthetic.dmg'},
                'dmg': ['synthetic-image'], 'lxml_candidate': provenance}

    run = module.subprocess.run

    def only_native_inspection(command, **kwargs):
        if command[0] in ('otool', 'nm'):
            return run(command, **kwargs)
        calls.append(command[0])

    monkeypatch.setattr(module, 'prepare_build', prepare)
    monkeypatch.setattr(module, 'validate_sparkle_distribution', lambda path: path)
    monkeypatch.setattr(module, 'bundle_plist', lambda value: {})
    monkeypatch.setattr(module, 'embed_sparkle', lambda *args: None)
    monkeypatch.setattr(module.subprocess, 'run', only_native_inspection)
    monkeypatch.setattr(module, 'sign_app', lambda *args: calls.append('sign'))
    monkeypatch.setattr(module, 'stage_image', lambda *args: None)
    argv = ['--out', str(tmp_path / 'out'), '--sparkle-distribution', str(sdk)]
    if local_preview:
        assert module.main([*argv, '--local-preview']) == 0
    else:
        with pytest.raises(RuntimeError, match='publication blocked'):
            module.main(argv)
        assert calls == ['synthetic-freezer'], 'public build must stop before signing/image'

    destination = app / 'Contents/Resources/ThirdPartyNotices'
    report = json.loads((destination / 'manifest.json').read_text())
    names = {d['name'] for d in report['distributions']}
    assert 'lxml' in names, 'shipped staged candidate is missing from notice distribution index'
    assert names == {'lxml', 'pypdf', 'proxy-tools', 'pyinstaller'}
    lxml = next(d for d in report['distributions'] if d['name'] == 'lxml')
    assert lxml['version'] == installed.version
    assert lxml['selection'] == 'analysis-toc'
    for relative, data in expected.items():
        notice = next(n for n in lxml['notices'] if n['file'].endswith('/' + relative))
        assert (destination / notice['file']).read_bytes() == data
        assert notice['sha256'] == hashlib.sha256(data).hexdigest()
    assert len(report['native_binaries']) == 2
    assert all(n['file'].startswith('Contents/Frameworks/lxml/') for n in report['native_binaries'])
    assert {'artifact-selection-review', 'native-runtime-review', 'proxy-tools-license-conflict'} <= {
        b['id'] for b in report['blockers']}
    assert report['release_ready'] is False
    assert str(tmp_path) not in json.dumps(report)
    text = (destination / 'THIRD_PARTY_NOTICES.md').read_text()
    assert f"## lxml {installed.version}" in text
    assert all(n['file'] in text for n in lxml['notices'])
    if local_preview:
        build = json.loads((tmp_path / 'out/Synthetic.build.json').read_text())
        assert build['publication_blocked'] is True
        assert build['license_blockers'] == report['blockers']


def test_missing_sdk_license_fails_even_for_local_preview(tmp_path):
    app = tmp_path / 'Synthetic.app'
    app.mkdir()
    with pytest.raises(RuntimeError, match='SDK license'):
        builder().collect_bundle_notices(app, tmp_path / 'sdk', tmp_path / 'Analysis.toc', local_preview=True)
