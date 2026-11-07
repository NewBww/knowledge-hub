"""Fetch and verify the fixed official Sparkle SDK (never bundled signing tools)."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tarfile
import urllib.request
from pathlib import Path


VERSION = '2.10.1'
ARCHIVE_NAME = f'Sparkle-{VERSION}.tar.xz'
URL = f'https://github.com/sparkle-project/Sparkle/releases/download/{VERSION}/{ARCHIVE_NAME}'
SHA256 = '1a856d2a9edb8e628de88121d7be04cf0e2167f8641650b78fca00b14244cf27'


def verify_archive(archive: Path) -> None:
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != SHA256:
        raise RuntimeError(f'Sparkle archive SHA-256 mismatch; expected {SHA256}')


def extract_verified(archive: Path, destination: Path) -> None:
    verify_archive(archive)
    if destination.exists():
        raise RuntimeError('Sparkle destination already exists; refusing to merge SDKs')
    destination.mkdir(parents=True)
    try:
        with tarfile.open(archive, 'r:xz') as stream:
            stream.extractall(destination, filter='data')
    except BaseException:
        shutil.rmtree(destination)
        raise


def validate_distribution(distribution: Path) -> Path:
    """Re-hash original archive and compare every embedded file/link before build."""
    distribution = distribution.expanduser().resolve()
    archive = distribution.parent / ARCHIVE_NAME
    verify_archive(archive)
    expected = set()
    with tarfile.open(archive, 'r:xz') as stream:
        for member in stream.getmembers():
            relative = Path(member.name)
            if not relative.parts or relative.parts[0] != 'Sparkle.framework' or member.isdir():
                continue
            expected.add(relative)
            target = distribution / relative
            if member.issym():
                valid = target.is_symlink() and os.readlink(target) == member.linkname
            elif member.isfile():
                valid = target.is_file() and not target.is_symlink()
                if valid:
                    with target.open('rb') as actual, stream.extractfile(member) as original:
                        valid = (hashlib.file_digest(actual, 'sha256').digest() ==
                                 hashlib.file_digest(original, 'sha256').digest())
                    valid = valid and (target.stat().st_mode & 0o111) == (member.mode & 0o111)
            else:
                valid = False
            if not valid:
                raise RuntimeError(f'Sparkle distribution differs from pinned archive: {relative}')
    framework = distribution / 'Sparkle.framework'
    actual = {p.relative_to(distribution) for p in framework.rglob('*')
              if p.is_symlink() or not p.is_dir()}
    if not expected or actual != expected:
        raise RuntimeError('Sparkle framework contents differ from pinned archive')
    return framework


def fetch(destination: Path) -> Path:
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / ARCHIVE_NAME
    if not archive.exists():
        partial = archive.with_suffix('.part')
        try:
            with urllib.request.urlopen(URL, timeout=60) as response, partial.open('wb') as stream:
                shutil.copyfileobj(response, stream)
            verify_archive(partial)
            partial.replace(archive)
        finally:
            partial.unlink(missing_ok=True)
    distribution = destination / 'distribution'
    if not distribution.exists():
        extract_verified(archive, distribution)
    validate_distribution(distribution)
    return distribution


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='SDK cache outside the application bundle')
    args = parser.parse_args(argv)
    print(fetch(args.out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
