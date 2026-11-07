"""Local release preparation; official Keychain integration is explicitly opt-in."""
import base64
import datetime as dt
import hashlib
import xml.etree.ElementTree as ET
import importlib.util
import json
import os
import plistlib
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_tool():
    path = ROOT / 'tools/prepare_release.py'
    assert path.is_file(), 'local release preparation tool is missing'
    spec = importlib.util.spec_from_file_location('prepare_release', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def artifact(tmp_path):
    dmg = tmp_path / 'Knowledge-Hub-1.2.3-macos-arm64.dmg'
    dmg.write_bytes(b'Synthetic fixture, not an installer')
    manifest = dmg.with_suffix('.build.json')
    manifest.write_text(json.dumps({'version': '1.2.3', 'architecture': 'arm64',
                                    'artifact': dmg.name, 'bundle_id': 'com.knowledgehub.desktop'}))
    return dmg, manifest, hashlib.sha256(dmg.read_bytes()).hexdigest()


@pytest.mark.parametrize('change', ['prerelease', 'path-version', 'leading-zero', 'digest',
                                    'same-version', 'downgrade', 'bad-previous',
                                    'manifest-version', 'manifest-arch', 'manifest-name',
                                    'manifest-bundle', 'dmg-name', 'symlink'])
def test_release_validation_rejects_unbound_or_unstable_inputs(artifact, change):
    tool = load_tool()
    dmg, manifest, digest = artifact
    version, previous = '1.2.3', '1.2.2'
    data = json.loads(manifest.read_text())
    if change == 'prerelease': version = '1.2.3-rc1'
    if change == 'path-version': version = '../1.2.3'
    if change == 'leading-zero': version = '01.2.3'
    if change == 'digest': digest = '0' * 64
    if change == 'same-version': previous = '1.2.3'
    if change == 'downgrade': previous = '1.3.0'
    if change == 'bad-previous': previous = 'v1.2.2'
    if change == 'manifest-version': data['version'] = '1.2.2'
    if change == 'manifest-arch': data['architecture'] = 'x86_64'
    if change == 'manifest-name': data['artifact'] = 'other.dmg'
    if change == 'manifest-bundle': data['bundle_id'] = 'other.app'
    manifest.write_text(json.dumps(data))
    if change == 'dmg-name': dmg = dmg.rename(dmg.with_name('wrong.dmg'))
    if change == 'symlink':
        target = dmg.rename(dmg.with_name('target.dmg'))
        dmg.symlink_to(target)
    with pytest.raises(ValueError):
        tool.validate_inputs(dmg, manifest, version, digest, previous)


def test_rendered_feed_has_stable_platform_pinned_asset_and_inert_notes(artifact):
    tool = load_tool()
    dmg, manifest, digest = artifact
    release = tool.validate_inputs(dmg, manifest, '1.2.3', digest)
    signature = base64.b64encode(bytes(64)).decode()  # serialization fixture, not a valid signature
    now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    xml = tool.render_appcast(release, signature, '12.0.0', '<script>alert(1)</script> & text', now)
    root = ET.fromstring(xml)
    ns = {'s': tool.SPARKLE_NS}
    item = root.find('channel/item')
    assert item.find('s:version', ns).text == '1.2.3'
    assert item.find('s:shortVersionString', ns).text == '1.2.3'
    assert item.find('s:minimumSystemVersion', ns).text == '12.0.0'
    assert item.find('s:hardwareRequirements', ns).text == 'arm64'
    assert item.find('s:channel', ns) is None  # default stable, never prerelease
    enclosure = item.find('enclosure')
    assert enclosure.attrib == {'url': release['url'], 'length': str(release['length']),
                                'type': 'application/octet-stream',
                                f'{{{tool.SPARKLE_NS}}}edSignature': signature,
                                f'{{{tool.SPARKLE_NS}}}os': 'macos'}
    description = item.find('description')
    assert description.attrib == {f'{{{tool.SPARKLE_NS}}}format': 'plain-text'}
    assert description.text == '<script>alert(1)</script> & text'
    assert len(description) == 0
    assert b'<script>' not in xml
    assert root.find('channel/link').text == tool.FEED_URL


@pytest.mark.parametrize('minimum,signature,notes', [
    ('11.0.0', base64.b64encode(bytes(64)).decode(), ''),
    ('12.0', base64.b64encode(bytes(64)).decode(), ''),
    ('12.0.0', 'invalid', ''),
    ('12.0.0', base64.b64encode(bytes(64)).decode(), 'bad\x00text'),
    ('12.0.0', base64.b64encode(bytes(64)).decode(), 'https://untrusted.invalid/notes'),
])
def test_feed_rejects_bad_minimum_signature_encoding_and_xml_controls(artifact, minimum, signature, notes):
    tool = load_tool()
    dmg, manifest, digest = artifact
    with pytest.raises(ValueError):
        tool.render_appcast(tool.validate_inputs(dmg, manifest, '1.2.3', digest),
                            signature, minimum, notes, dt.datetime.now(dt.timezone.utc))


def make_bundle(tool, parent):
    app = parent / 'Knowledge Hub.app'
    (app / 'Contents/MacOS').mkdir(parents=True)
    (app / 'Contents/MacOS/Knowledge Hub').write_bytes(b'synthetic executable fixture')
    (app / 'Contents/Frameworks/Sparkle.framework').mkdir(parents=True)
    metadata = {'CFBundleVersion': '1.2.3', 'CFBundleShortVersionString': '1.2.3',
                'CFBundleIdentifier': 'com.knowledgehub.desktop', 'CFBundleExecutable': 'Knowledge Hub',
                'LSMinimumSystemVersion': '12.0.0', 'SUFeedURL': tool.FEED_URL,
                'SUPublicEDKey': tool.PUBLIC_KEY, 'SURequireSignedFeed': True,
                'SUSignedFeedFailureExpirationInterval': 0, 'SUVerifyUpdateBeforeExtraction': True,
                'SUEnableAutomaticChecks': False, 'SUAutomaticallyUpdate': False,
                'SUAllowsAutomaticUpdates': False, 'SUEnableSystemProfiling': False}
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(metadata))
    return app


@pytest.mark.parametrize('bad', [None, 'version', 'short-version', 'publisher', 'feed', 'signed-feed',
                               'expiry', 'pre-extract', 'automatic', 'minimum', 'executable-path',
                               'architecture', 'framework'])
def test_bundle_inspection_binds_archive_metadata_and_update_policy(tmp_path, monkeypatch, bad):
    tool = load_tool()
    app = make_bundle(tool, tmp_path)
    plist = app / 'Contents/Info.plist'
    data = plistlib.loads(plist.read_bytes())
    changes = {'version': ('CFBundleVersion', '1.2.2'),
               'short-version': ('CFBundleShortVersionString', '1.2.2'),
               'publisher': ('SUPublicEDKey', 'untrusted'), 'feed': ('SUFeedURL', 'https://other.invalid'),
               'signed-feed': ('SURequireSignedFeed', False),
               'expiry': ('SUSignedFeedFailureExpirationInterval', 60),
               'pre-extract': ('SUVerifyUpdateBeforeExtraction', False),
               'automatic': ('SUAllowsAutomaticUpdates', True),
               'minimum': ('LSMinimumSystemVersion', '13.0.0'),
               'executable-path': ('CFBundleExecutable', '../bad')}
    if bad in changes:
        key, value = changes[bad]
        data[key] = value
        plist.write_bytes(plistlib.dumps(data))
    if bad == 'framework': (app / 'Contents/Frameworks/Sparkle.framework').rmdir()
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(
        a, 0, stdout='x86_64\n' if bad == 'architecture' else 'arm64\n'))
    if bad:
        with pytest.raises(ValueError):
            tool.inspect_bundle(app, '1.2.3', '12.0.0')
    else:
        tool.inspect_bundle(app, '1.2.3', '12.0.0')


@pytest.mark.skipif(not os.environ.get('KH_SPARKLE_BIN'), reason='explicit official Keychain signing opt-in required')
def test_official_prepare_signs_real_synthetic_dmg_and_feed_rejects_tampering(tmp_path, monkeypatch):
    tool = load_tool()
    bins = Path(os.environ['KH_SPARKLE_BIN'])
    image_source = tmp_path / 'image.noindex'
    app = make_bundle(tool, image_source)
    binary = app / 'Contents/MacOS/Knowledge Hub'
    binary.unlink()
    subprocess.run(['/usr/bin/cc', '-arch', 'arm64', '-x', 'c', '-', '-o', str(binary)],
                    input=b'int main(void) { return 0; }\n', check=True)
    dmg = tmp_path / 'Knowledge-Hub-1.2.3-macos-arm64.dmg'
    subprocess.run(['/usr/bin/hdiutil', 'create', '-quiet', '-srcfolder', str(image_source),
                    '-format', 'UDZO', str(dmg)], check=True)
    manifest = dmg.with_suffix('.build.json')
    manifest.write_text(json.dumps({'version': '1.2.3', 'architecture': 'arm64',
                                    'artifact': dmg.name, 'bundle_id': 'com.knowledgehub.desktop'}))
    digest = hashlib.sha256(dmg.read_bytes()).hexdigest()
    output = tmp_path / 'release'
    result = tool.main(['--version', '1.2.3', '--dmg', str(dmg), '--build-manifest', str(manifest),
                        '--sha256', digest, '--previous-version', '1.2.2', '--output', str(output),
                        '--sparkle-bin', str(bins), '--scratch', str(tmp_path)])
    assert result == 0
    assert sorted(p.name for p in output.iterdir()) == [dmg.name, 'SHA256SUMS', 'appcast.xml', 'release.json']
    assert (output / dmg.name).read_bytes() == dmg.read_bytes()
    report = json.loads((output / 'release.json').read_text())
    assert report['sha256'] == digest
    assert report['publisher_public_key'] == tool.PUBLIC_KEY
    assert report['feed_url'] == tool.FEED_URL
    assert report['length'] == dmg.stat().st_size
    assert report['previous_version'] == '1.2.2'
    assert report['published'] is False
    assert report['notarized'] is False
    command = [str(bins / 'sign_update'), '--account', tool.ACCOUNT, '--verify']
    subprocess.run(command + [str(output / dmg.name), report['ed_signature']], check=True)
    subprocess.run(command + [str(output / 'appcast.xml')], check=True)
    for path in [output / dmg.name, output / 'appcast.xml']:
        data = path.read_bytes()
        path.write_bytes(data.replace(b'Knowledge Hub', b'Knowledge Hux', 1)
                         if path.suffix == '.xml' else data + b'tamper')
        arguments = [str(path)] + ([report['ed_signature']] if path.suffix != '.xml' else [])
        rejected = subprocess.run(command + arguments, capture_output=True)
        assert rejected.returncode != 0, 'official verifier accepted a modified signed asset'
        path.write_bytes(data)
    sums = (output / 'SHA256SUMS').read_text()
    for name in [dmg.name, 'appcast.xml', 'release.json']:
        assert f'{hashlib.sha256((output / name).read_bytes()).hexdigest()}  {name}\n' in sums
    failed_output = tmp_path / 'failed-release'
    def interrupted_copy(source, target, **kwargs):
        target.mkdir(exist_ok=True)
        (target / 'partial').write_text('interrupted')
        raise OSError('synthetic interrupted output copy')
    monkeypatch.setattr(tool.shutil, 'copytree', interrupted_copy)
    with pytest.raises(SystemExit):
        tool.main(['--version', '1.2.3', '--dmg', str(dmg), '--build-manifest', str(manifest),
                   '--sha256', digest, '--output', str(failed_output),
                   '--sparkle-bin', str(bins), '--scratch', str(tmp_path)])
    assert not failed_output.exists(), 'failed preparation left publishable-looking partial output'


def cli_args(artifact, tmp_path):
    dmg, manifest, digest = artifact
    return ['--version', '1.2.3', '--dmg', str(dmg), '--build-manifest', str(manifest),
            '--sha256', digest, '--output', str(tmp_path / 'release'),
            '--sparkle-bin', str(tmp_path / 'trusted-tools'), '--scratch', str(tmp_path)]


def test_cli_refuses_wrong_key_before_any_signing_or_mounting(artifact, tmp_path, monkeypatch):
    tool = load_tool()
    monkeypatch.setattr(tool.sys, 'platform', 'darwin')
    commands = []
    def wrong_key(bins, program, *args):
        commands.append((program, args))
        return 'untrusted public key'
    monkeypatch.setattr(tool, 'sparkle', wrong_key)
    with pytest.raises(SystemExit) as result:
        tool.main(cli_args(artifact, tmp_path))
    assert result.value.code == 2
    assert commands == [('generate_keys', ('-p',))]
    assert not (tmp_path / 'release').exists()


def test_cli_preserves_existing_output_before_keychain_access(artifact, tmp_path, monkeypatch):
    tool = load_tool()
    output = tmp_path / 'release'
    output.mkdir()
    (output / 'sentinel').write_text('keep')
    def forbidden(*args): raise AssertionError('must not access Keychain')
    monkeypatch.setattr(tool, 'sparkle', forbidden)
    with pytest.raises(SystemExit):
        tool.main(cli_args(artifact, tmp_path))
    assert (output / 'sentinel').read_text() == 'keep'


def test_mount_is_readonly_detached_after_bundle_rejection(tmp_path, monkeypatch):
    tool = load_tool()
    mount = tmp_path / 'mount.noindex'
    mount.mkdir()
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(ValueError):
        tool.inspect_dmg(tmp_path / 'synthetic.dmg', mount, '1.2.3', '12.0.0')
    assert '-readonly' in commands[1]
    assert '-nobrowse' in commands[1]
    assert commands[-1] == ['/usr/bin/hdiutil', 'detach', str(mount)]


@pytest.mark.parametrize('component', ['Contents', 'Contents/Info.plist', 'Contents/MacOS'])
def test_bundle_metadata_must_not_follow_links_outside_archive(tmp_path, monkeypatch, component):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a, 0, stdout='arm64'))
    tool = load_tool()
    app = make_bundle(tool, tmp_path)
    source = app / component
    external = tmp_path / 'outside'
    source.rename(external)
    source.symlink_to(external, target_is_directory=external.is_dir())
    with pytest.raises(ValueError):
        tool.inspect_bundle(app, '1.2.3', '12.0.0')


def test_validated_release_binds_explicit_version_digest_and_build_manifest(artifact):
    tool = load_tool()
    dmg, manifest, digest = artifact
    release = tool.validate_inputs(dmg, manifest, '1.2.3', digest, '1.2.2')
    assert release == {'version': '1.2.3', 'tag': 'v1.2.3', 'architecture': 'arm64',
                       'artifact': dmg.name, 'sha256': digest, 'length': dmg.stat().st_size,
                       'url': 'https://github.com/NewBww/knowledge-hub/releases/download/v1.2.3/' + dmg.name}
