"""Collect notices for an explicit frozen artifact using its build environment.

Run with the SAME Python environment as PyInstaller. Selection is explicit:
installed development packages are never assumed to have shipped.
"""
from __future__ import annotations

import hashlib
import ast
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import sys
import sysconfig
import subprocess

ASSETS = Path(__file__).resolve().parents[1] / 'assets/licenses'
MACHO_MAGICS = {bytes.fromhex(v) for v in ('feedface', 'cefaedfe', 'feedfacf', 'cffaedfe',
                                          'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}


class LicenseError(ValueError):
    """Required distribution or complete license text is unavailable."""


def canonical(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def collect(bundle: Path, destination: Path, *, required_distributions: list[str] | None = None,
            analysis_toc: Path | None = None, site_packages: list[str] | None = None,
            python_license: Path | None = None) -> dict:
    bundle, destination = Path(bundle), Path(destination)
    if not bundle.is_dir():
        raise LicenseError('bundle must be an existing directory')
    if (destination.is_symlink() or destination.resolve() == bundle.resolve()
            or (destination.exists() and (not destination.is_dir() or any(destination.iterdir())))
            or any(parent.is_symlink() for parent in destination.parents)):
        raise LicenseError('destination must be a fresh directory without symlink parents')
    distributions = metadata.distributions() if site_packages is None else metadata.distributions(path=site_packages)
    installed = {canonical(d.metadata['Name']): d for d in distributions}
    selected = {canonical(name): 'explicit' for name in (required_distributions or [])}
    if analysis_toc is not None:
        owners = {}
        for name, dist in installed.items():
            if name == 'knowledge-hub':
                continue
            for entry in dist.files or []:
                owners.setdefault(str(Path(str(dist.locate_file(entry))).resolve()), set()).add(name)
        def visit(value):
            if isinstance(value, (tuple, list)):
                if (len(value) == 3 and all(isinstance(v, str) for v in value)
                        and value[2].startswith(('PYMODULE', 'EXTENSION', 'BINARY', 'DATA'))):
                    for owner in owners.get(str(Path(value[1]).resolve()), []):
                        selected.setdefault(owner, 'analysis-toc')
                else:
                    for child in value:
                        visit(child)
        try:
            visit(ast.literal_eval(Path(analysis_toc).read_text()))
        except (ValueError, SyntaxError) as exc:
            raise LicenseError('invalid PyInstaller Analysis TOC') from exc
    if not selected:
        raise LicenseError('provide a nonempty explicit distribution list or Analysis TOC')
    selected['pyinstaller'] = 'bootloader'
    report = {'schema_version': 1, 'selection': 'explicit artifact distribution list; not all installed packages',
              'distributions': [], 'runtime': {}, 'native_binaries': [], 'blockers': [],
              'release_ready': False}
    report['blockers'].append({'id': 'artifact-selection-review',
        'detail': 'Reconcile the selected distributions and native inventory with this exact frozen artifact; '
                  'TOC ownership is evidence, not proof of complete dependency/license coverage.'})
    report['blockers'].append({'id': 'native-runtime-review',
        'detail': 'Audit bundled CPython/native build provenance and embedded libraries, '
                  'including compiler runtimes and statically linked dependencies; CPython LICENSE alone is insufficient.'})
    payload = {}
    supplemental = json.loads((ASSETS / 'SOURCES.json').read_text())
    for native in sorted(bundle.rglob('*')):
        if native.is_symlink():
            if not native.resolve().is_relative_to(bundle.resolve()):
                raise LicenseError('bundle contains an external symlink; native inventory would be incomplete')
            continue
        if not native.is_file():
            continue
        with native.open('rb') as stream:
            magic = stream.read(4)
        if magic not in MACHO_MAGICS:
            continue
        try:
            links = subprocess.run(['otool', '-L', str(native)], check=True,
                                   capture_output=True, text=True).stdout
            symbols = subprocess.run(['nm', '-a', str(native)], check=True,
                                     capture_output=True, text=True).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise LicenseError('native inspection failed; macOS otool and nm are required') from exc
        static_iconv = bool(re.search(r' [TtDd] _+libiconv_(?:open|version)\b', symbols))
        report['native_binaries'].append({
            'file': native.relative_to(bundle).as_posix(),
            'sha256': hashlib.sha256(native.read_bytes()).hexdigest(),
            'linked_libraries': sorted({Path(line.strip().split(' (compatibility')[0]).name
                                        for line in links.splitlines() if line.startswith('\t')}),
            'static_iconv_symbols': static_iconv,
        })
        if static_iconv:
            report['blockers'].append({'id': 'lgpl-iconv-relinking',
                'file': native.relative_to(bundle).as_posix(),
                'detail': 'Static GNU libiconv detected. Provide corresponding source, patches, '
                          'build scripts and a tested relinkable object/source route under LGPL-2.1 section 6; '
                          'a source URL or license text alone is insufficient.'})
    for name in sorted(selected):
        if name not in installed:
            raise LicenseError(f'required distribution not installed: {name}')
        dist = installed[name]
        notices = []
        for entry in sorted(dist.files or [], key=str):
            rel = Path(str(entry))
            if (rel.suffix.lower() in {'.so', '.dylib', '.dll', '.a', '.o', '.py', '.pyc', '.pyo', '.plist', '.yml'}
                    or any(part.endswith('.dSYM') for part in rel.parts)):
                continue
            if not (re.match(r'^(license|licence|copying|notice|authors)([._-].*|s)?$', rel.name, re.I)
                    or 'licenses' in {part.lower() for part in rel.parts}):
                continue
            if rel.is_absolute() or '..' in rel.parts:
                raise LicenseError(f'unsafe license record path: {name}')
            data = Path(str(dist.locate_file(entry))).read_bytes()
            if not data.strip():
                raise LicenseError(f'empty license text: {name}')
            output = f'licenses/{name}/installed/{rel.as_posix()}'
            payload[output] = data
            notices.append({'file': output, 'sha256': hashlib.sha256(data).hexdigest()})
        if name in supplemental:
            supplement = supplemental[name]
            if supplement['version'] != dist.version:
                raise LicenseError(f'supplemental notices need review for {name} {dist.version}')
            for relative, expected in supplement.get('installed_files', {}).items():
                if hashlib.sha256(Path(str(dist.locate_file(relative))).read_bytes()).hexdigest() != expected:
                    raise LicenseError(f'supplemental source identity mismatch: {name}')
            report['blockers'].extend(supplement.get('blockers', []))
            for notice in supplement['notices']:
                data = (ASSETS / notice['file']).read_bytes()
                if hashlib.sha256(data).hexdigest() != notice['sha256']:
                    raise LicenseError(f'supplemental notice checksum mismatch: {name}')
                output = 'licenses/' + notice['file']
                payload[output] = data
                notices.append({**notice, 'file': output})
        if not any(re.match(r'^(license|licence|copying)([._-].*|s)?$', Path(n['file']).name, re.I)
                   for n in notices):
            raise LicenseError(f'required license text missing: {name} {dist.version}')
        report['distributions'].append({'name': name, 'version': dist.version,
                                        'selection': selected[name],
                                        'notices': notices,
                                        **({'source': supplemental[name]['source'],
                                            'source_notice': supplemental[name]['source_notice']}
                                           if name in supplemental and 'source' in supplemental[name] else {})})
    runtime_license = python_license or Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt'
    data = runtime_license.read_bytes()
    if not data.strip():
        raise LicenseError('empty CPython runtime license')
    payload['licenses/CPython/LICENSE.txt'] = data
    report['runtime'] = {'name': 'CPython', 'version': sys.version.split()[0],
                         'notices': [{'file': 'licenses/CPython/LICENSE.txt',
                                      'sha256': hashlib.sha256(data).hexdigest()}]}
    for notice in supplemental.get('_runtime', {}).get(report['runtime']['version'], []):
        relative = Path(notice['file'])
        if relative.is_absolute() or '..' in relative.parts:
            raise LicenseError('unsafe runtime supplemental notice path')
        data = (ASSETS / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != notice['sha256']:
            raise LicenseError('runtime supplemental notice checksum mismatch')
        output = 'licenses/' + relative.as_posix()
        payload[output] = data
        report['runtime']['notices'].append({**notice, 'file': output})
    text = '# Third-party notices\n\nNot a legal clearance or a complete native dependency audit.\n\n'
    text += 'Includes the PyInstaller Bootloader Exception; see the full COPYING.txt below.\n\n'
    for dist in report['distributions']:
        text += f"## {dist['name']} {dist['version']}\n\n"
        for notice in dist['notices']:
            text += f"- [{notice['file']}]({notice['file']})\n"
        if 'source' in dist:
            text += f"\n{dist['source_notice']}\n\nSource: {dist['source']['url']}\n\nSHA-256: `{dist['source']['sha256']}`\n"
    if 'pillow' in selected:
        text += ('\nThis software is based in part on the work of the Independent JPEG Group.\n'
                 'This software is based in part on the work of the FreeType Team (https://freetype.org/).\n')
    text += '\n## CPython\n\n[Full runtime license](licenses/CPython/LICENSE.txt)\n'
    for notice in report['runtime']['notices'][1:]:
        text += f"- [{notice['file']}]({notice['file']})\n"
    text += '\n## Release prerequisites (unresolved)\n\n'
    for blocker in report['blockers']:
        text += f"- **{blocker['id']}**: {blocker['detail']}\n"
    payload['THIRD_PARTY_NOTICES.md'] = text.encode()
    payload['manifest.json'] = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    destination.mkdir(parents=True, exist_ok=True)
    for relative, data in payload.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--distribution', action='append', default=[],
                        help='Required shipped distribution; repeat or use --analysis-toc')
    parser.add_argument('--analysis-toc', type=Path, help='Exact build PyInstaller Analysis-00.toc')
    parser.add_argument('--site-packages', action='append', help='Explicit distribution metadata environment')
    parser.add_argument('--python-license', type=Path, help='Full LICENSE.txt from the bundled CPython runtime')
    args = parser.parse_args(argv)
    try:
        report = collect(args.bundle, args.destination, required_distributions=args.distribution,
                         analysis_toc=args.analysis_toc, site_packages=args.site_packages,
                         python_license=args.python_license)
    except LicenseError as exc:
        print(f'BLOCKED: {exc}', file=sys.stderr)
        return 2
    except OSError:
        print('BLOCKED: required notice/metadata input cannot be read or output cannot be written', file=sys.stderr)
        return 2
    print(f"Collected {len(report['distributions'])} distribution notices and "
          f"{len(report['native_binaries'])} native binary records. "
          f"BLOCKED: {len(report['blockers'])} release prerequisites; see manifest.json.")
    return 2 if report['blockers'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
