"""Build a host-architecture, ad-hoc signed macOS app and drag-install DMG."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import plistlib
import subprocess
import tempfile
import shutil
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAME = 'Knowledge Hub'
WEB_SUFFIXES = {'.html', '.css', '.js', '.svg', '.png', '.ico', '.woff', '.woff2'}


def stage_lxml_candidate(wheel: Path, sha256: str, evidence: Path, destination: Path) -> dict:
    """Stage a candidate without installing it or granting publication clearance."""
    import hashlib
    import io
    import re
    import stat
    import struct
    import zipfile
    for path in (wheel, evidence, destination):
        if '..' in path.parts or any(p.is_symlink() for p in (path, *path.absolute().parents)):
            raise ValueError('Candidate paths must not traverse symlinks or parents')
    if destination.exists():
        raise ValueError('Candidate staging requires a fresh destination')
    if not sha256 or not re.fullmatch('[0-9a-f]{64}', sha256):
        raise ValueError('Explicit lowercase SHA-256 is required')
    tag = f'cp{sys.version_info.major}{sys.version_info.minor}'
    if (sys.platform != 'darwin' or platform.machine() != 'arm64' or
            sys.implementation.name != 'cpython' or
            wheel.name != f'lxml-6.1.3-{tag}-{tag}-macosx_12_0_arm64.whl'):
        raise ValueError('Candidate runtime/architecture mismatch')
    wheel_bytes = wheel.read_bytes()
    if hashlib.sha256(wheel_bytes).hexdigest() != sha256:
        raise ValueError('Candidate wheel SHA-256 mismatch')
    evidence_bytes = evidence.read_bytes()
    try:
        report = json.loads(evidence_bytes)
        if (report['wheel']['sha256'] != sha256 or Path(report['wheel']['file']).name != wheel.name or
                report['status'] != 'candidate-verified-not-release-cleared' or
                report['release_ready'] is not False or report['publication_blocked'] is not True or
                report['python'].split()[0] != platform.python_version() or
                len(report['commands']) != 7 or any(c['returncode'] != 0 for c in report['commands']) or
                '--with-schematron' not in report['commands'][0]['argv']):
            raise ValueError('Stale or incomplete candidate evidence')
        spec = importlib.util.spec_from_file_location('lxml_source_builder', ROOT / 'tools/build_lxml_macos.py')
        native_builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native_builder)
        for name, (url, digest) in native_builder.SOURCES.items():
            if report['sources'][name]['sha256'] != digest or report['sources'][name]['url'] != url:
                raise ValueError('Source provenance mismatch')
        native_builder.validate_versions(report['probe'])
        if report['probe']['docx']['status'] != 'extracted' or not report['probe']['docx']['text']:
            raise ValueError('Missing successful extraction probe')
        natives = {item['file']: item for item in report['native']}
        suffix = f'cpython-{sys.version_info.major}{sys.version_info.minor}-darwin.so'
        if len(report['native']) != 2 or set(natives) != {f'etree.{suffix}', f'objectify.{suffix}'}:
            raise ValueError('Incomplete native inventory')
        with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            if len(names) != len(set(names)):
                raise ValueError('Duplicate candidate archive members')
            files = {}
            for item in members:
                path = Path(item.filename)
                kind = stat.S_IFMT(item.external_attr >> 16)
                if (path.is_absolute() or '..' in path.parts or '\\' in item.filename or
                        kind not in (0, stat.S_IFREG, stat.S_IFDIR) or
                        path.parts[0] not in ('lxml', 'lxml-6.1.3.dist-info') or
                        item.file_size > 100 * 1024 * 1024):
                    raise ValueError('Unsafe candidate archive member')
                if not item.is_dir():
                    files[item.filename] = archive.read(item)
            expected_native = {'lxml/' + name for name in natives}
            payload_native = {name for name in files if name.endswith(('.so', '.dylib'))}
            allowed_native = expected_native | {f'lxml/{name}.{suffix}' for name in ('builder', '_elementpath', 'sax', 'html/_difflib', 'html/diff')}
            if not expected_native <= payload_native or not payload_native <= allowed_native:
                raise ValueError('Unexpected native payload')
            for name in payload_native:
                data = files[name]
                if len(data) < 32 or struct.unpack('<II', data[:8]) != (0xfeedfacf, 0x100000c):
                    raise ValueError('Native payload architecture mismatch')
            for name, item in natives.items():
                data = files['lxml/' + name]
                if (hashlib.sha256(data).hexdigest() != item['sha256'] or
                        len(data) < 32 or struct.unpack('<II', data[:8]) != (0xfeedfacf, 0x100000c) or
                        item['static_iconv_symbols'] is not False or
                        sorted(item['linked_libraries']) != ['/usr/lib/libSystem.B.dylib', '/usr/lib/libiconv.2.dylib', '/usr/lib/libz.1.dylib']):
                    raise ValueError('Native bytes/architecture/linkage evidence mismatch')
            if (f'Tag: {tag}-{tag}-macosx_12_0_arm64' not in files['lxml-6.1.3.dist-info/WHEEL'].decode() or
                    'Version: 6.1.3' not in files['lxml-6.1.3.dist-info/METADATA'].decode() or
                    'lxml/__init__.py' not in files):
                raise ValueError('Candidate metadata mismatch')
    except (KeyError, TypeError, IndexError, AttributeError, zipfile.BadZipFile) as error:
        raise ValueError('Incomplete candidate evidence or wheel') from error
    destination.mkdir(parents=True)
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {'wheel_file': wheel.name, 'wheel_sha256': sha256,
            'evidence_sha256': hashlib.sha256(evidence_bytes).hexdigest(),
            'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
            'native': report['native'],
            'sources': {name: {'url': item['url'], 'sha256': item['sha256']} for name, item in report['sources'].items()},
            'release_ready': False, 'publication_blocked': True}


def build_metadata(root: Path) -> dict:
    project = tomllib.loads((root / 'pyproject.toml').read_text())['project']
    version = project['version']
    arch = platform.machine()
    return {'version': version, 'architecture': arch,
            'artifact': f'Knowledge-Hub-{version}-macos-{arch}.dmg',
            'bundle_id': 'com.knowledgehub.desktop'}


def stage_sources(root: Path, destination: Path) -> Path:
    """Copy only application code and public UI assets, never a repo/data tree."""
    source = root / 'src/knowledge_hub'
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(source)
        if '__pycache__' in relative.parts:
            continue
        if path.suffix != '.py' and not (
            relative.parts[0] == 'web' and path.suffix in WEB_SUFFIXES
        ):
            continue
        target = destination / 'knowledge_hub' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return destination


def bundle_plist(metadata: dict) -> dict:
    policy = json.loads((ROOT / 'assets/releases/macos.json').read_text())['bundle_policy']
    return {**policy, 'CFBundleShortVersionString': metadata['version'],
            'CFBundleVersion': metadata['version'],
            'CFBundleIdentifier': metadata['bundle_id'],
            'NSHighResolutionCapable': True,
            'CFBundleIconFile': 'KnowledgeHub.icns'}


def pyinstaller_command(stage: Path, out: Path, work: Path, metadata: dict) -> list[str]:
    return [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
            '--onedir', '--windowed', '--name', NAME,
            '--icon', str(ROOT / 'assets/macos/KnowledgeHub.icns'),
            '--distpath', str(out), '--workpath', str(work / 'build'),
            '--specpath', str(work), '--paths', str(stage),
            '--osx-bundle-identifier', metadata['bundle_id'],
            '--target-architecture', metadata['architecture'],
            '--collect-all', 'webview',
            '--hidden-import', 'webview.platforms.cocoa',
            '--hidden-import', 'Security',
            '--hidden-import', 'PyObjCTools.AppHelper',
            '--hidden-import', 'uvicorn.loops.asyncio',
            '--hidden-import', 'uvicorn.protocols.http.h11_impl',
            '--hidden-import', 'uvicorn.lifespan.on',
            '--add-data', f'{stage / "knowledge_hub/web"}:knowledge_hub/web',
            str(stage / 'desktop_entry.py')]


def verify_lxml_selection(analysis_toc: Path, candidate: Path, provenance: dict) -> None:
    """Fail before notices/signing if Analysis selected any upstream lxml bytes."""
    import ast
    import hashlib
    found = set()
    def visit(value):
        if isinstance(value, (list, tuple)):
            if len(value) == 3 and all(isinstance(v, str) for v in value):
                name, source, kind = value
                if name == 'lxml' or name.startswith(('lxml.', 'lxml/')):
                    path = Path(source)
                    try:
                        relative = path.relative_to(candidate).as_posix()
                    except ValueError as error:
                        raise ValueError('Upstream lxml selection in Analysis') from error
                    if (path.is_symlink() or relative not in provenance['files'] or
                            hashlib.sha256(path.read_bytes()).hexdigest() != provenance['files'][relative]):
                        raise ValueError('Changed lxml selection bytes')
                    found.add(relative)
            else:
                for item in value:
                    visit(item)
    visit(ast.literal_eval(analysis_toc.read_text()))
    if not {'lxml/' + item['file'] for item in provenance['native']} <= found:
        raise ValueError('Incomplete native lxml selection')


def prepare_build(root: Path, out: Path, work: Path, *, lxml_wheel: Path | None = None,
                  lxml_sha256: str | None = None, lxml_evidence: Path | None = None) -> dict:
    selection = (lxml_wheel, lxml_sha256, lxml_evidence)
    if any(v is not None for v in selection) and not all(v is not None for v in selection):
        raise ValueError('Candidate wheel, SHA-256 and evidence are required together')
    provenance = None
    candidate = work / 'lxml-candidate'
    if lxml_wheel is not None:
        assert lxml_sha256 is not None and lxml_evidence is not None
        provenance = stage_lxml_candidate(lxml_wheel, lxml_sha256, lxml_evidence, candidate)
    if not (root / 'src/knowledge_hub/web/index.html').is_file():
        raise RuntimeError('UI index.html is missing; build the public UI first')
    metadata = build_metadata(root)
    stage = stage_sources(root, work / 'source')
    (stage / 'desktop_entry.py').write_text('from knowledge_hub.cli import main\nraise SystemExit(main())\n')
    out.mkdir(parents=True, exist_ok=True)
    image = out / metadata['artifact']
    image_stage = work / 'image.noindex'
    freezer_out = work / 'freeze.noindex'
    command = pyinstaller_command(stage, freezer_out, work, metadata)
    if provenance is not None:
        manifest = work / 'lxml-candidate-provenance.json'
        manifest.write_text(json.dumps(provenance, indent=2) + '\n')
        # The freezer AND hook subprocesses must see this package before site-packages.
        wrapper = work / 'freeze_candidate.py'
        wrapper.write_text('import hashlib, json, pathlib, runpy, sys\n'
            f'candidate = pathlib.Path({str(candidate)!r})\n'
            f'provenance = json.loads(pathlib.Path({str(manifest)!r}).read_text())\n'
            'for name, digest in provenance["files"].items():\n'
            '    path = candidate / name\n'
            '    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:\n'
            '        raise RuntimeError("Candidate changed before freezing")\n'
            'sys.path.insert(0, str(candidate))\n'
            'import lxml\n'
            'assert pathlib.Path(lxml.__file__).is_relative_to(candidate)\n'
            'runpy.run_module("PyInstaller", run_name="__main__")\n')
        command = [sys.executable, '-E', '-s', str(wrapper), '--paths', str(candidate),
                   '--hidden-import', 'lxml.etree', '--hidden-import', 'lxml.objectify',
                   '--add-data', f'{candidate / "lxml-6.1.3.dist-info"}:lxml-6.1.3.dist-info',
                   *command[3:]]
    return {**({'lxml_candidate': provenance} if provenance else {}),
            'metadata': metadata, 'stage': stage, 'app': freezer_out / f'{NAME}.app',
            'image': image, 'image_stage': image_stage,
            'pyinstaller': command,
            'dmg': ['hdiutil', 'create', '-volname', NAME, '-srcfolder', str(image_stage),
                    '-ov', '-format', 'UDZO', str(image)]}


def stage_image(app: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    shutil.copytree(app, destination / f'{NAME}.app', symlinks=True)
    (destination / 'Applications').symlink_to('/Applications', target_is_directory=True)


def validate_sparkle_distribution(distribution: Path) -> Path:
    # Also works when this builder is imported by path, without tools on sys.path.
    spec = importlib.util.spec_from_file_location('fetch_sparkle', ROOT / 'tools/fetch_sparkle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_distribution(distribution)


def embed_sparkle(app: Path, distribution: Path) -> None:
    framework = validate_sparkle_distribution(distribution)
    destination = app / 'Contents/Frameworks/Sparkle.framework'
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(framework, destination, symlinks=True)


def collect_bundle_notices(app: Path, distribution: Path, analysis_toc: Path, *,
                           collector=None, local_preview: bool = False) -> dict:
    license_path = distribution / 'LICENSE'
    if license_path.is_symlink() or not license_path.is_file() or not license_path.stat().st_size:
        raise RuntimeError('Verified Sparkle SDK license is missing')
    if collector is None:
        spec = importlib.util.spec_from_file_location('collect_licenses', ROOT / 'tools/collect_licenses.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        collector = module.collect
    destination = app / 'Contents/Resources/ThirdPartyNotices'
    report = collector(app, destination, analysis_toc=analysis_toc)
    license_bytes = license_path.read_bytes()
    (destination / 'Sparkle-LICENSE.txt').write_bytes(license_bytes)
    import hashlib
    report['frameworks'] = [{'name': 'Sparkle', 'version': '2.10.1',
                             'license_file': 'Sparkle-LICENSE.txt',
                             'license_sha256': hashlib.sha256(license_bytes).hexdigest()}]
    (destination / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    with (destination / 'THIRD_PARTY_NOTICES.md').open('a') as stream:
        stream.write('\n## Sparkle 2.10.1\n\nSee [complete SDK license](Sparkle-LICENSE.txt).\n')
    if not local_preview and (report['blockers'] or not report['release_ready']):
        raise RuntimeError('Binary publication blocked; inspect bundled ThirdPartyNotices/manifest.json')
    return report


def sign_app(app: Path) -> None:
    framework = app / 'Contents/Frameworks/Sparkle.framework'
    version = framework / 'Versions/B'
    # Never --deep-sign the distribution: helper entitlements must survive.
    nested = [version / 'XPCServices/Installer.xpc',
              version / 'XPCServices/Downloader.xpc',
              version / 'Autoupdate', version / 'Updater.app', framework]
    for target in nested:
        subprocess.run(['codesign', '--force', '--sign', '-', '--options', 'runtime',
                        '--preserve-metadata=entitlements', str(target)], check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'dist')
    parser.add_argument('--sparkle-distribution', type=Path,
                        help='Verified official SDK directory; pinned archive must be in its parent')
    parser.add_argument('--dry-run', action='store_true', help='Print build configuration without invoking packaging tools')
    parser.add_argument('--lxml-candidate-wheel', type=Path, help='Opt-in isolated native lxml wheel (not release clearance)')
    parser.add_argument('--lxml-candidate-sha256', help='Required exact candidate wheel SHA-256')
    parser.add_argument('--lxml-candidate-evidence', type=Path, help='Required native builder evidence bound to this wheel')
    parser.add_argument('--local-preview', action='store_true',
                        help='Build isolated local QA output with unresolved license blockers recorded; not for publication')
    args = parser.parse_args(argv)
    if sys.platform != 'darwin':
        parser.error('macOS is required (WebKit, codesign and hdiutil)')
    if not args.dry_run:
        if platform.machine() != 'arm64':
            parser.error('Stable macOS releases currently support arm64 only')
        if args.sparkle_distribution is None:
            parser.error('--sparkle-distribution is required for a native-update build')
        validate_sparkle_distribution(args.sparkle_distribution)
    out = args.out.expanduser().resolve()
    # Respect the workspace scratch policy; no user appdata is read or copied.
    scratch = Path(os.environ.get('TMPDIR') or Path.home() / '.cache/knowledge-hub-build')
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='knowledge-hub-build-', suffix='.noindex', dir=scratch) as temporary:
        candidate_args = {}
        if any(v is not None for v in (args.lxml_candidate_wheel, args.lxml_candidate_sha256, args.lxml_candidate_evidence)):
            candidate_args = dict(lxml_wheel=args.lxml_candidate_wheel,
                                  lxml_sha256=args.lxml_candidate_sha256,
                                  lxml_evidence=args.lxml_candidate_evidence)
        plan = prepare_build(ROOT, out, Path(temporary), **candidate_args)
        if args.dry_run:
            print(json.dumps(plan, default=str, indent=2))
            return 0
        subprocess.run(plan['pyinstaller'], cwd=plan['stage'], check=True)
        if 'lxml_candidate' in plan:
            verify_lxml_selection(Path(temporary) / 'build/Knowledge Hub/Analysis-00.toc',
                                  Path(temporary) / 'lxml-candidate', plan['lxml_candidate'])
        app = plan['app']
        plist_path = app / 'Contents/Info.plist'
        with plist_path.open('rb') as stream:
            plist = plistlib.load(stream)
        plist.update(bundle_plist(plan['metadata']))
        with plist_path.open('wb') as stream:
            plistlib.dump(plist, stream)
        embed_sparkle(app, args.sparkle_distribution)
        notices = collect_bundle_notices(app, args.sparkle_distribution,
                                         Path(temporary) / 'build/Knowledge Hub/Analysis-00.toc',
                                         local_preview=args.local_preview)
        if 'lxml_candidate' in plan:
            (app / 'Contents/Resources/lxml-candidate-provenance.json').write_text(
                json.dumps(plan['lxml_candidate'], indent=2) + '\n')
            if not args.local_preview:
                raise RuntimeError('Candidate publication blocked pending exact frozen native/license review')
        sign_app(app)
        stage_image(app, plan['image_stage'])
        subprocess.run(plan['dmg'], check=True)
        subprocess.run(['hdiutil', 'verify', str(plan['image'])], check=True)
        (out / f"{plan['image'].stem}.build.json").write_text(
            json.dumps({**plan['metadata'], **({'lxml_candidate': plan['lxml_candidate']} if 'lxml_candidate' in plan else {}), **({'local_preview': True,
                'publication_blocked': True, 'license_blockers': notices['blockers']}
                if args.local_preview else {})}, indent=2) + '\n')
        print(f"Built {plan['image']}\nTemporary app staging removed after packaging.\nAd-hoc local-test signature only; not notarized.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
