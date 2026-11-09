"""Build a labelled, reproducible pywebview backport wheel offline.

This creates an opt-in dependency candidate, never redistribution clearance.
The ordinary project lock and the caller's installed environment are unchanged.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

ASSETS = Path(__file__).resolve().parents[1] / 'assets/vendor/pywebview'
WHEEL_SHA256 = '9d07275f53894ab4d5e2e0e996227193e7187dec276d9b624dccbce029216b46'
INIT_SHA256 = '53a631a579ce342fb45efbe4ef024b28deabb34f061bcf058fd818ce27aa7e80'
PATCHED_SHA256 = 'e3cab490f013ceb447b0e0943fe049fa825272fdcbc0fd285d10f8849da60941'
LICENSE_SHA256 = '4a988dd3598832cd3653de20dc33cb677d0fb53ab5551c879ca31280ae653675'
VERSION = '6.2.1+kh.1'


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_candidate(wheel: Path, destination: Path) -> dict:
    wheel, destination = Path(wheel), Path(destination)
    raw = wheel.read_bytes()
    if sha256(raw) != WHEEL_SHA256:
        raise ValueError('locked upstream wheel checksum mismatch')
    provenance = json.loads((ASSETS / 'PROVENANCE.json').read_text())
    patched = (ASSETS / '__init__.py').read_bytes()
    license_bytes = (ASSETS / 'LICENSE').read_bytes()
    if (sha256(patched) != PATCHED_SHA256 or sha256(license_bytes) != LICENSE_SHA256
            or provenance['patched_init_sha256'] != PATCHED_SHA256
            or provenance['license_sha256'] != LICENSE_SHA256
            or provenance['version'] != VERSION):
        raise ValueError('backport source or license checksum mismatch')
    old = 'pywebview-6.2.1.dist-info/'
    new = f'pywebview-{VERSION}.dist-info/'
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate wheel members')
        for entry in archive.infolist():
            path = Path(entry.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                    or not entry.filename.startswith(('webview/', old))):
                raise ValueError('unsafe wheel member')
            if not entry.is_dir():
                name = new + entry.filename[len(old):] if entry.filename.startswith(old) else entry.filename
                files[name] = archive.read(entry)
    if sha256(files['webview/__init__.py']) != INIT_SHA256:
        raise ValueError('upstream initializer checksum mismatch')
    metadata_name = new + 'METADATA'
    text = files[metadata_name].decode()
    if text.count('\nVersion: 6.2.1\n') != 1 or text.count('\nRequires-Dist: proxy_tools\n') != 1:
        raise ValueError('unexpected upstream version or dependency metadata')
    text = text.replace('\nVersion: 6.2.1\n', f'\nVersion: {VERSION}\n')
    files[metadata_name] = text.replace('\nRequires-Dist: proxy_tools\n', '\n').encode()
    files['webview/__init__.py'] = patched
    files[new + 'licenses/KNOWLEDGE-HUB-BACKPORT-LICENSE'] = license_bytes
    files[new + 'knowledge_hub_backport.json'] = (json.dumps(provenance, sort_keys=True, indent=2) + '\n').encode()
    record_name = new + 'RECORD'
    files.pop(record_name, None)
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, content in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip('=')
        writer.writerow([name, 'sha256=' + digest, str(len(content))])
    writer.writerow([record_name, '', ''])
    files[record_name] = record.getvalue().encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compresslevel=9)
    filename = f'pywebview-{VERSION}-py3-none-any.whl'
    evidence = {'version': VERSION, 'wheel_file': filename, 'wheel_sha256': sha256(output.getvalue()),
                'upstream_wheel_sha256': sha256(raw), 'backport': provenance,
                'release_ready': False, 'publication_blocked': True}
    if destination.exists() or any(p.is_symlink() for p in (destination, *destination.absolute().parents)):
        raise ValueError('candidate output requires a fresh directory without symlink parents')
    destination.mkdir(parents=True)
    (destination / filename).write_bytes(output.getvalue())
    (destination / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True, help='Exact wheel pinned by uv.lock')
    parser.add_argument('--out', type=Path, required=True, help='Fresh output directory')
    args = parser.parse_args(argv)
    print(json.dumps(build_candidate(args.wheel, args.out), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
