"""Prepare local signed GitHub release assets; never publishes or uploads."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import email.utils
import hashlib
import xml.etree.ElementTree as ET
import json
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY = 'https://github.com/NewBww/knowledge-hub'
FEED_URL = REPOSITORY + '/releases/latest/download/appcast.xml'
PUBLIC_KEY = 'eRN7w0nSTjTGD/AIwzhAYCE7Ltgm+3yqxlWK1CP11fQ='
ACCOUNT = 'com.knowledgehub.desktop.release'
SPARKLE_NS = 'http://www.andymatuschak.org/xml-namespaces/sparkle'
ET.register_namespace('sparkle', SPARKLE_NS)


def render_appcast(release: dict, signature: str, minimum: str, notes: str,
                   published: dt.datetime) -> bytes:
    if stable_version(minimum) < (12, 0, 0):
        raise ValueError('minimum macOS version cannot be below 12.0.0')
    if len(base64.b64decode(signature, validate=True)) != 64:
        raise ValueError('expected a 64-byte Ed25519 signature')
    if any(not (c in '\t\n\r' or '\x20' <= c <= '\ud7ff' or '\ue000' <= c <= '\ufffd'
                or '\U00010000' <= c <= '\U0010ffff') for c in notes):
        raise ValueError('release notes contain XML control characters')
    if notes.lstrip().lower().startswith(('http://', 'https://')):
        raise ValueError('notes must not begin with a URL (Sparkle legacy remote-notes fallback)')
    root = ET.Element('rss', {'version': '2.0'})
    channel = ET.SubElement(root, 'channel')
    ET.SubElement(channel, 'title').text = 'Knowledge Hub stable updates'
    ET.SubElement(channel, 'link').text = FEED_URL
    item = ET.SubElement(channel, 'item')
    ET.SubElement(item, 'title').text = 'Knowledge Hub ' + release['version']
    ET.SubElement(item, 'pubDate').text = email.utils.format_datetime(published, usegmt=True)
    for tag, text in [('version', release['version']), ('shortVersionString', release['version']),
                      ('minimumSystemVersion', minimum), ('hardwareRequirements', 'arm64')]:
        ET.SubElement(item, f'{{{SPARKLE_NS}}}{tag}').text = text
    ET.SubElement(item, 'description', {f'{{{SPARKLE_NS}}}format': 'plain-text'}).text = notes
    ET.SubElement(item, 'enclosure', {
        'url': release['url'], 'length': str(release['length']), 'type': 'application/octet-stream',
        f'{{{SPARKLE_NS}}}edSignature': signature, f'{{{SPARKLE_NS}}}os': 'macos',
    })
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)



def inspect_bundle(app: Path, version: str, minimum: str) -> None:
    """Inspect the mounted archive, not a caller-supplied loose app or manifest."""
    if app.is_symlink() or any((app / part).is_symlink() for part in
                               ('Contents', 'Contents/Info.plist', 'Contents/MacOS')):
        raise ValueError('bundle metadata paths must not be symlinks')
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    expected = {'CFBundleVersion': version, 'CFBundleShortVersionString': version,
                'CFBundleIdentifier': 'com.knowledgehub.desktop',
                'SUFeedURL': FEED_URL, 'SUPublicEDKey': PUBLIC_KEY,
                'SURequireSignedFeed': True, 'SUSignedFeedFailureExpirationInterval': 0,
                'SUVerifyUpdateBeforeExtraction': True, 'SUEnableAutomaticChecks': False,
                'SUAutomaticallyUpdate': False, 'SUAllowsAutomaticUpdates': False,
                'SUEnableSystemProfiling': False}
    for key, value in expected.items():
        if key not in info or type(info[key]) is not type(value) or info[key] != value:
            raise ValueError(f'archive bundle policy mismatch: {key}')
    if stable_version(minimum) < max((12, 0, 0), stable_version(info.get('LSMinimumSystemVersion', ''))):
        raise ValueError('feed minimum must cover the bundle minimum macOS version')
    executable = info.get('CFBundleExecutable', '')
    if not executable or Path(executable).name != executable or executable in {'.', '..'}:
        raise ValueError('unsafe bundle executable path')
    binary = app / 'Contents/MacOS' / executable
    if binary.is_symlink() or not binary.is_file():
        raise ValueError('bundle executable must be a regular file')
    if not (app / 'Contents/Frameworks/Sparkle.framework').is_dir():
        raise ValueError('bundled Sparkle framework is missing')
    architecture = subprocess.run(['/usr/bin/lipo', '-archs', str(binary)],
                                  capture_output=True, text=True, check=True).stdout.strip()
    if architecture != 'arm64':
        raise ValueError('archive executable must be arm64 only')


def inspect_publication_readiness(app: Path) -> None:
    """Require exact bundled compliance evidence before preparing public assets.

    This is a gate, never a mechanism for granting legal clearance. The collector
    remains fail-closed until separately reviewed artifact evidence is available.
    """
    notices = app / 'Contents/Resources/ThirdPartyNotices'
    manifest = notices / 'manifest.json'
    if any(path.is_symlink() for path in (app / 'Contents/Resources', notices, manifest)):
        raise ValueError('bundled compliance paths must not be symlinks')
    try:
        report = json.loads(manifest.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError('bundled compliance report is missing or invalid') from exc
    if (not isinstance(report, dict) or report.get('release_ready') is not True
            or report.get('blockers') != []):
        raise ValueError('bundled compliance review is unresolved; publication blocked')
    # Ad-hoc integrity is not publisher trust. Require Apple's Developer ID
    # Application chain, Gatekeeper acceptance, and an offline stapled ticket.
    requirement = ('anchor apple generic and '
                   'certificate 1[field.1.2.840.113635.100.6.2.6] exists and '
                   'certificate leaf[field.1.2.840.113635.100.6.1.13] exists')
    checks = [
        ['/usr/bin/codesign', '--verify', '--deep', '--strict', '-R', requirement, str(app)],
        ['/usr/sbin/spctl', '--assess', '--type', 'execute', str(app)],
        ['/usr/bin/xcrun', 'stapler', 'validate', str(app)],
    ]
    for command in checks:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError('Developer ID signature, Gatekeeper acceptance and stapled notarization '
                             'are required; publication blocked') from exc


def stable_version(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError('version must be stable MAJOR.MINOR.PATCH without a tag prefix')
    major, minor, patch = (int(part) for part in value.split('.'))
    return major, minor, patch


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_inputs(dmg: Path, manifest: Path, version: str, digest: str,
                    previous_version: str | None = None) -> dict:
    current = stable_version(version)
    if previous_version is not None and current <= stable_version(previous_version):
        raise ValueError('release must be newer than the previous stable version')
    if dmg.is_symlink() or not dmg.is_file() or manifest.is_symlink() or not manifest.is_file():
        raise ValueError('artifact and manifest must be regular files, not symlinks')
    expected_name = f'Knowledge-Hub-{version}-macos-arm64.dmg'
    data = json.loads(manifest.read_text())
    if dmg.name != expected_name or data != {
        'version': version, 'architecture': 'arm64', 'artifact': expected_name,
        'bundle_id': 'com.knowledgehub.desktop',
    }:
        raise ValueError('artifact name, version and build metadata must match')
    actual_digest = sha256(dmg)
    if not re.fullmatch(r'[0-9a-f]{64}', digest) or actual_digest != digest:
        raise ValueError('explicit SHA-256 does not match artifact')
    if not dmg.stat().st_size:
        raise ValueError('artifact is empty')
    return {'version': version, 'tag': 'v' + version, 'architecture': data['architecture'],
            'artifact': dmg.name, 'sha256': actual_digest,
            'length': dmg.stat().st_size,
            'url': f'{REPOSITORY}/releases/download/v{version}/{dmg.name}'}


def sparkle(bins: Path, tool: str, *arguments: str) -> str:
    """Only official Keychain APIs; no private-key flags, stdin, export or logging."""
    result = subprocess.run([str(bins / tool), '--account', ACCOUNT, *arguments],
                            capture_output=True, text=True, check=True, timeout=120)
    return result.stdout.strip()


def inspect_dmg(dmg: Path, mount: Path, version: str, minimum: str) -> None:
    subprocess.run(['/usr/bin/hdiutil', 'verify', '-quiet', str(dmg)], check=True)
    subprocess.run(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-noautoopen',
                    '-mountpoint', str(mount), str(dmg)], check=True, capture_output=True)
    try:
        apps = list(mount.glob('*.app'))
        if len(apps) != 1 or apps[0].name != 'Knowledge Hub.app' or apps[0].is_symlink():
            raise ValueError('archive must contain exactly Knowledge Hub.app')
        inspect_bundle(apps[0], version, minimum)
        inspect_publication_readiness(apps[0])
    finally:
        subprocess.run(['/usr/bin/hdiutil', 'detach', str(mount)], check=True, capture_output=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, help='Explicit stable MAJOR.MINOR.PATCH')
    parser.add_argument('--dmg', required=True, type=Path)
    parser.add_argument('--build-manifest', required=True, type=Path)
    parser.add_argument('--sha256', required=True, help='Independently reviewed artifact SHA-256')
    parser.add_argument('--previous-version', help='Last approved stable version; enforces increase')
    parser.add_argument('--minimum-system-version', default='12.0.0')
    parser.add_argument('--release-notes-text', type=Path, help='UTF-8 plain text, never HTML')
    parser.add_argument('--sparkle-bin', required=True, type=Path, help='Trusted official Sparkle 2.10.1 bin directory')
    parser.add_argument('--scratch', required=True, type=Path, help='Approved local scratch directory')
    parser.add_argument('--output', required=True, type=Path, help='New directory; existing paths are never replaced')
    args = parser.parse_args(argv)
    try:
        if sys.platform != 'darwin':
            raise ValueError('local macOS and the approved Keychain account are required')
        if args.output.exists() or args.output.is_symlink():
            raise ValueError('output must be a new directory')
        release = validate_inputs(args.dmg, args.build_manifest, args.version, args.sha256, args.previous_version)
        if stable_version(args.minimum_system_version) < (12, 0, 0):
            raise ValueError('minimum macOS version cannot be below 12.0.0')
        notes = args.release_notes_text.read_text(encoding='utf-8') if args.release_notes_text else ''
        if sparkle(args.sparkle_bin, 'generate_keys', '-p') != PUBLIC_KEY:
            raise ValueError('Keychain publisher public key does not match pinned key; nothing signed')
        with tempfile.TemporaryDirectory(prefix='knowledge-hub-release-', suffix='.noindex', dir=args.scratch) as temporary:
            work = Path(temporary)
            staged = work / 'release'
            staged.mkdir()
            archive = staged / release['artifact']
            shutil.copyfile(args.dmg, archive)
            # Re-hash our private staging snapshot before mounting or signing it.
            if sha256(archive) != release['sha256']:
                raise ValueError('archive changed while copying')
            inspect_dmg(archive, work / 'mount.noindex', args.version, args.minimum_system_version)
            signature = sparkle(args.sparkle_bin, 'sign_update', '-p', str(archive))
            sparkle(args.sparkle_bin, 'sign_update', '--verify', str(archive), signature)
            feed = staged / 'appcast.xml'
            feed.write_bytes(render_appcast(release, signature, args.minimum_system_version, notes,
                                             dt.datetime.now(dt.timezone.utc)))
            sparkle(args.sparkle_bin, 'sign_update', str(feed))
            sparkle(args.sparkle_bin, 'sign_update', '--verify', str(feed))
            report = dict(release, ed_signature=signature, publisher_public_key=PUBLIC_KEY,
                          feed_url=FEED_URL, minimum_system_version=args.minimum_system_version,
                          previous_version=args.previous_version, published=False, notarized=False)
            (staged / 'release.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
            sums = ''.join(f'{sha256(path)}  {path.name}\n'
                           for path in sorted(staged.iterdir()))
            (staged / 'SHA256SUMS').write_text(sums)
            # Reserve the destination exclusively; clean only the directory we created.
            args.output.mkdir()
            try:
                shutil.copytree(staged, args.output, dirs_exist_ok=True)
            except BaseException:
                shutil.rmtree(args.output)
                raise
        print(f'Prepared verified local assets in {args.output}. Nothing published; not notarized.')
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
