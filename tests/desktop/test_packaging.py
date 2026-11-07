import importlib.util
import platform
import sys
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def synthetic_arm64_host(monkeypatch):
    """Reach mocked build stages; this is not native arm64 build acceptance."""
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(platform, 'machine', lambda: 'arm64')


def builder():
    spec = importlib.util.spec_from_file_location('desktop_builder', ROOT / 'tools/build_macos.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetcher():
    spec = importlib.util.spec_from_file_location('fetch_sparkle', ROOT / 'tools/fetch_sparkle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sparkle_distribution_must_match_pinned_archive_before_embedding(tmp_path, monkeypatch):
    import hashlib
    import io
    import tarfile
    import pytest
    module = fetcher()
    archive = tmp_path / module.ARCHIVE_NAME
    with tarfile.open(archive, 'w:xz') as stream:
        data = b'Synthetic framework binary'
        member = tarfile.TarInfo('./Sparkle.framework/Versions/B/Sparkle')
        member.size = len(data)
        member.mode = 0o755
        stream.addfile(member, io.BytesIO(data))
        link = tarfile.TarInfo('./Sparkle.framework/Sparkle')
        link.type = tarfile.SYMTYPE
        link.linkname = 'Versions/B/Sparkle'
        stream.addfile(link)
    distribution = tmp_path / 'distribution'
    with pytest.raises(RuntimeError, match='SHA-256'):
        module.extract_verified(archive, distribution)
    assert not distribution.exists()
    monkeypatch.setattr(module, 'SHA256', hashlib.sha256(archive.read_bytes()).hexdigest())
    module.extract_verified(archive, distribution)
    assert module.validate_distribution(distribution) == distribution / 'Sparkle.framework'
    assert (distribution / 'Sparkle.framework/Sparkle').is_symlink()
    (distribution / 'Sparkle.framework/Versions/B/Sparkle').write_bytes(b'tampered')
    with pytest.raises(RuntimeError, match='differs'):
        module.validate_distribution(distribution)


def test_fetch_sparkle_downloads_only_pinned_https_asset(tmp_path, monkeypatch):
    import io
    import pytest
    module = fetcher()
    urls = []
    monkeypatch.setattr(module.urllib.request, 'urlopen',
                        lambda url, timeout: (urls.append(url) or io.BytesIO(b'invalid archive')))
    with pytest.raises(RuntimeError, match='SHA-256'):
        module.fetch(tmp_path)
    assert urls == ['https://github.com/sparkle-project/Sparkle/releases/download/2.10.1/Sparkle-2.10.1.tar.xz']
    assert not (tmp_path / 'distribution').exists()


def test_bundle_plist_enforces_manual_signed_archive_and_feed_policy():
    import json
    from knowledge_hub.native_updater import BUNDLE_POLICY
    module = builder()
    plist = module.bundle_plist(module.build_metadata(ROOT))
    for key, value in BUNDLE_POLICY.items():
        assert plist.get(key) == value, key
    public = json.loads((ROOT / 'assets/releases/macos.json').read_text())
    assert public['bundle_policy'] == BUNDLE_POLICY
    assert public['sparkle']['sha256'] == fetcher().SHA256
    assert 'PyObjCTools.AppHelper' in module.pyinstaller_command(
        ROOT, ROOT, ROOT, module.build_metadata(ROOT))


def test_embed_preserves_framework_links_without_shipping_sdk_tools(tmp_path, monkeypatch):
    module = builder()
    distribution = tmp_path / 'sdk/distribution'
    framework = distribution / 'Sparkle.framework'
    (framework / 'Versions/B/Resources').mkdir(parents=True)
    (framework / 'Versions/B/Sparkle').write_text('Synthetic')
    (framework / 'Versions/Current').symlink_to('B')
    (framework / 'Sparkle').symlink_to('Versions/Current/Sparkle')
    (distribution / 'bin').mkdir()
    (distribution / 'bin/sign_update').write_text('DO NOT SHIP')
    app = tmp_path / 'Synthetic.app'
    app.mkdir()
    monkeypatch.setattr(module, 'validate_sparkle_distribution', lambda path: framework)
    module.embed_sparkle(app, distribution)
    embedded = app / 'Contents/Frameworks/Sparkle.framework'
    assert (embedded / 'Sparkle').is_symlink()
    assert (embedded / 'Versions/Current').readlink() == Path('B')
    assert not list(app.rglob('sign_update'))
    assert not list(app.rglob('generate_keys'))


def test_signing_is_inside_out_preserves_entitlements_and_only_verifies_deep(tmp_path, monkeypatch):
    module = builder()
    commands = []
    monkeypatch.setattr(module.subprocess, 'run', lambda command, **kwargs: commands.append(command))
    app = tmp_path / 'Synthetic.app'
    module.sign_app(app)
    signed = [command for command in commands if '--sign' in command]
    assert [Path(command[-1]).name for command in signed] == [
        'Installer.xpc', 'Downloader.xpc', 'Autoupdate', 'Updater.app', 'Sparkle.framework', 'Synthetic.app']
    assert all('--deep' not in command for command in signed)
    assert all('--preserve-metadata=entitlements' in command for command in signed[:-1])
    assert commands[-1] == ['codesign', '--verify', '--deep', '--strict', str(app)]


def test_package_metadata_and_allowlisted_boundary(tmp_path):
    module = builder()
    metadata = module.build_metadata(ROOT)
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    assert metadata['version'] == version
    assert metadata['architecture'] == platform.machine()
    assert metadata['artifact'] == f'Knowledge-Hub-{version}-macos-{platform.machine()}.dmg'
    assert metadata['bundle_id'] == 'com.knowledgehub.desktop'
    source = tmp_path / 'source'
    package = source / 'src/knowledge_hub'
    (package / 'web').mkdir(parents=True)
    (package / 'desktop.py').write_text('# launcher')
    (package / 'web/index.html').write_text('<html></html>')
    (package / 'web/app.js').write_text('void 0;')
    (package / 'agent.token').write_text('PRIVATE')
    (package / 'knowledge.sqlite3').write_text('PRIVATE')
    (source / 'private-notes.md').write_text('PRIVATE')
    staged = module.stage_sources(source, tmp_path / 'stage')
    assert sorted(str(p.relative_to(staged)) for p in staged.rglob('*') if p.is_file()) == [
        'knowledge_hub/desktop.py', 'knowledge_hub/web/app.js', 'knowledge_hub/web/index.html'
    ]


def test_pyinstaller_plan_is_windowed_onedir_and_includes_webkit(tmp_path):
    module = builder()
    stage = tmp_path / 'stage'
    args = module.pyinstaller_command(stage, tmp_path / 'out', tmp_path / 'work',
                                      module.build_metadata(ROOT))
    assert '--onedir' in args
    assert '--windowed' in args
    assert '--clean' in args
    assert args[args.index('--collect-all') + 1] == 'webview'
    assert 'webview.platforms.cocoa' in args
    assert 'Security' in args
    import tomllib
    dependencies = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['optional-dependencies']['desktop']
    assert any(value.startswith('pyobjc-framework-Security') for value in dependencies)
    assert 'uvicorn.loops.asyncio' in args
    assert '--target-architecture' in args
    assert f'{stage / "knowledge_hub/web"}:knowledge_hub/web' in args
    assert args[-1] == str(stage / 'desktop_entry.py')
    plist = module.bundle_plist(module.build_metadata(ROOT))
    assert plist['CFBundleShortVersionString'] == module.build_metadata(ROOT)['version']
    assert plist['CFBundleIdentifier'] == 'com.knowledgehub.desktop'
    assert plist['NSHighResolutionCapable'] is True


def test_prepare_build_drag_install_image_has_only_app_and_applications_link(tmp_path):
    module = builder()
    root = tmp_path / 'repo'
    (root / 'src/knowledge_hub/web').mkdir(parents=True)
    (root / 'src/knowledge_hub/web/index.html').write_text('<html></html>')
    (root / 'src/knowledge_hub/desktop.py').write_text('def launch(): pass')
    (root / 'pyproject.toml').write_text('[project]\nversion="1.2.3"\n')
    plan = module.prepare_build(root, tmp_path / 'out', tmp_path / 'work')
    assert (plan['stage'] / 'desktop_entry.py').read_text() == (
        'from knowledge_hub.cli import main\nraise SystemExit(main())\n')
    assert '--windowed' in plan['pyinstaller']
    assert plan['dmg'][:3] == ['hdiutil', 'create', '-volname']
    assert '-srcfolder' in plan['dmg']
    assert '-format' in plan['dmg'] and 'UDZO' in plan['dmg']
    assert str(plan['image']) in plan['dmg']
    assert '1.2.3' in plan['image'].name
    app = tmp_path / 'fake.app'
    app.mkdir()
    (app / 'Contents').mkdir()
    module.stage_image(app, plan['image_stage'])
    assert sorted(p.name for p in plan['image_stage'].iterdir()) == ['Applications', 'Knowledge Hub.app']
    assert (plan['image_stage'] / 'Applications').readlink() == Path('/Applications')


def test_prepare_refuses_missing_ui_before_build(tmp_path):
    import pytest
    module = builder()
    with pytest.raises(RuntimeError, match='UI'):
        module.prepare_build(tmp_path, tmp_path / 'out', tmp_path / 'work')


def test_freezer_and_image_staging_are_ephemeral_noindex_not_distribution(tmp_path):
    module = builder()
    out = tmp_path / 'dist'
    work = tmp_path / 'temporary.noindex'
    plan = module.prepare_build(ROOT, out, work)
    freezer_out = Path(plan['pyinstaller'][plan['pyinstaller'].index('--distpath') + 1])
    assert freezer_out == work / 'freeze.noindex'
    assert plan['app'] == freezer_out / 'Knowledge Hub.app'
    assert plan['image_stage'] == work / 'image.noindex'
    assert plan['image'].parent == out
    assert not list(out.glob('*.app'))


def test_public_application_icon_contains_complete_retina_iconset(tmp_path):
    import struct
    icon = ROOT / 'assets/macos/KnowledgeHub.icns'
    data = icon.read_bytes()
    assert data[:4] == b'icns'
    assert struct.unpack('>I', data[4:8])[0] == len(data)
    chunks = set()
    offset = 8
    while offset < len(data):
        kind, size = struct.unpack('>4sI', data[offset:offset + 8])
        assert size >= 8
        chunks.add(kind)
        offset += size
    assert offset == len(data)
    # Apple's iconutil uses ARGB ic04/ic05 on this macOS, not PNG icp4/icp5.
    assert chunks & {b'ic04', b'icp4'}
    assert chunks & {b'ic05', b'icp5'}
    assert {b'ic07', b'ic08', b'ic09', b'ic10', b'ic11', b'ic12',
            b'ic13', b'ic14'} <= chunks
    assert (ROOT / 'assets/macos/KnowledgeHubIcon.swift').is_file()


def test_pyinstaller_and_bundle_plist_use_original_icns(tmp_path):
    module = builder()
    args = module.pyinstaller_command(tmp_path / 'stage', tmp_path / 'out',
                                      tmp_path / 'work', module.build_metadata(ROOT))
    assert '--icon' in args
    assert Path(args[args.index('--icon') + 1]) == ROOT / 'assets/macos/KnowledgeHub.icns'
    assert module.bundle_plist(module.build_metadata(ROOT))['CFBundleIconFile'] == 'KnowledgeHub.icns'


def test_native_iconutil_decodes_expected_sizes(tmp_path):
    import struct
    import subprocess
    import sys
    import pytest
    if sys.platform != 'darwin':
        pytest.skip('Apple iconutil is macOS-only')
    decoded = tmp_path / 'decoded.iconset'
    subprocess.run(['iconutil', '-c', 'iconset', '-o', str(decoded),
                    str(ROOT / 'assets/macos/KnowledgeHub.icns')], check=True)
    expected = {f'icon_{points}x{points}{suffix}.png': points * scale
                for points in (16, 32, 128, 256, 512)
                for scale, suffix in ((1, ''), (2, '@2x'))}
    assert {path.name for path in decoded.iterdir()} == set(expected)
    for filename, pixels in expected.items():
        data = (decoded / filename).read_bytes()
        assert data[:8] == b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II', data[16:24]) == (pixels, pixels)


def test_cli_dry_run_cleans_its_noindex_temporary_tree(tmp_path):
    import json
    import os
    import subprocess
    import sys
    import pytest
    if sys.platform != 'darwin':
        pytest.skip('Builder CLI requires macOS')
    scratch = tmp_path / 'scratch'
    result = subprocess.run([sys.executable, str(ROOT / 'tools/build_macos.py'),
                             '--out', str(tmp_path / 'dist'), '--dry-run'],
                            env={**os.environ, 'TMPDIR': str(scratch)},
                            capture_output=True, text=True, check=True)
    plan = json.loads(result.stdout)
    temporary = Path(plan['stage']).parent
    assert temporary.suffix == '.noindex'
    assert temporary.parent == scratch
    assert not temporary.exists()
    assert list(scratch.iterdir()) == []


def test_build_requires_explicit_validated_sparkle_sdk_before_freezing(tmp_path, monkeypatch, synthetic_arm64_host, capsys):
    import pytest
    module = builder()
    commands = []
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: commands.append(args))
    with pytest.raises(SystemExit) as error:
        module.main(['--out', str(tmp_path / 'out')])
    assert error.value.code == 2
    assert '--sparkle-distribution' in capsys.readouterr().err
    assert commands == []


def test_build_refuses_non_arm64_release_target_before_freezing(tmp_path, monkeypatch, capsys):
    import pytest
    module = builder()
    monkeypatch.setattr(module.sys, 'platform', 'darwin')
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    calls = []
    monkeypatch.setattr(module, 'validate_sparkle_distribution', lambda path: calls.append('validate'))
    monkeypatch.setattr(module, 'prepare_build', lambda *args: calls.append('prepare'))
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: calls.append('run'))
    out = tmp_path / 'out'
    with pytest.raises(SystemExit) as error:
        module.main(['--out', str(out), '--sparkle-distribution', str(tmp_path / 'sdk')])
    assert error.value.code == 2
    assert 'support arm64 only' in capsys.readouterr().err
    assert calls == []
    assert not out.exists()


def test_build_embeds_verified_framework_before_sign_and_image(tmp_path, monkeypatch, synthetic_arm64_host):
    import json
    import plistlib
    module = builder()
    monkeypatch.setenv('TMPDIR', str(tmp_path / 'scratch'))
    distribution = tmp_path / 'sdk/distribution'
    events = []
    monkeypatch.setattr(module, 'validate_sparkle_distribution', lambda path: events.append('validate'))
    monkeypatch.setattr(module, 'embed_sparkle', lambda app, path: events.append(('embed', path)))

    def notices(app, sdk, toc, *, local_preview):
        assert local_preview is True
        assert sdk == distribution
        assert toc.name == 'Analysis-00.toc'
        events.append('notices')
        return {'blockers': [{'id': 'synthetic-review'}], 'release_ready': False}

    monkeypatch.setattr(module, 'collect_bundle_notices', notices)

    def sign(app):
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        assert info['SURequireSignedFeed'] is True
        events.append('sign')

    monkeypatch.setattr(module, 'sign_app', sign)

    def run(command, **kwargs):
        if 'PyInstaller' in command:
            app = Path(command[command.index('--distpath') + 1]) / 'Knowledge Hub.app'
            (app / 'Contents').mkdir(parents=True)
            (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({}))
            events.append('freeze')
        elif command[:2] == ['hdiutil', 'create']:
            events.append('image')
        elif command[:2] == ['hdiutil', 'verify']:
            events.append('verify')

    monkeypatch.setattr(module.subprocess, 'run', run)
    assert module.main(['--out', str(tmp_path / 'out'), '--sparkle-distribution', str(distribution),
                        '--local-preview']) == 0
    assert events == ['validate', 'freeze', ('embed', distribution), 'notices', 'sign', 'image', 'verify']
    metadata = module.build_metadata(ROOT)
    receipt = json.loads((tmp_path / 'out' / (Path(metadata['artifact']).stem + '.build.json')).read_text())
    assert receipt['local_preview'] is True
    assert receipt['publication_blocked'] is True
    assert receipt['license_blockers'] == [{'id': 'synthetic-review'}]


def test_failed_freezer_cleans_its_temporary_bundle(tmp_path, monkeypatch, synthetic_arm64_host):
    import pytest
    module = builder()
    monkeypatch.setattr(module.sys, 'platform', 'darwin')
    scratch = tmp_path / 'scratch'
    monkeypatch.setenv('TMPDIR', str(scratch))

    def fail_freezer(command, **kwargs):
        freezer = Path(command[command.index('--distpath') + 1])
        (freezer / 'Knowledge Hub.app').mkdir(parents=True)
        raise RuntimeError('synthetic freezer failure')

    monkeypatch.setattr(module.subprocess, 'run', fail_freezer)
    monkeypatch.setattr(module, 'validate_sparkle_distribution', lambda path: path)
    with pytest.raises(RuntimeError, match='synthetic freezer failure'):
        module.main(['--out', str(tmp_path / 'dist'),
                     '--sparkle-distribution', str(tmp_path / 'synthetic-sdk')])
    assert list(scratch.iterdir()) == []
    assert not list((tmp_path / 'dist').glob('*.app'))


def test_build_script_has_runnable_cli():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, str(ROOT / 'tools/build_macos.py'), '--help'],
                            capture_output=True, text=True, check=True)
    assert '--out' in result.stdout
    assert '--dry-run' in result.stdout
