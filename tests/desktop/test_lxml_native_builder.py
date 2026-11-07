"""Scoped native-builder safety tests; no product build or network required."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]


def builder():
    spec = importlib.util.spec_from_file_location('native_builder', ROOT / 'tools/build_lxml_macos.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive(path, name, *, symlink=False):
    with tarfile.open(path, 'w') as stream:
        member = tarfile.TarInfo(name)
        if symlink:
            member.type = tarfile.SYMTYPE
            member.linkname = '/etc/passwd'
            stream.addfile(member)
        else:
            member.size = 4
            stream.addfile(member, io.BytesIO(b'test'))


def test_verified_source_extraction_rejects_bad_digest_before_writes(tmp_path):
    module = builder()
    source = tmp_path / 'source.tar'
    archive(source, 'source/README')
    target = tmp_path / 'unpacked'
    with pytest.raises(ValueError, match='SHA-256'):
        module.extract_verified(source, '0' * 64, target)
    assert not target.exists()


@pytest.mark.parametrize('name,symlink', [('../escape', False), ('source/link', True)])
def test_source_extraction_rejects_unsafe_members(tmp_path, name, symlink):
    module = builder()
    source = tmp_path / 'source.tar'
    archive(source, name, symlink=symlink)
    with pytest.raises(ValueError, match='Unsafe'):
        module.extract_verified(source, hashlib.sha256(source.read_bytes()).hexdigest(), tmp_path / 'unpacked')
    assert not (tmp_path / 'unpacked').exists()


def test_verified_source_extraction_preserves_regular_files(tmp_path):
    module = builder()
    source = tmp_path / 'source.tar'
    archive(source, 'source/README')
    root = module.extract_verified(source, hashlib.sha256(source.read_bytes()).hexdigest(), tmp_path / 'unpacked')
    assert (root / 'README').read_bytes() == b'test'


def test_explicit_native_build_dispatch_is_fail_closed(tmp_path, monkeypatch):
    module = builder()
    work = tmp_path / 'fresh'
    calls = []
    def probe(path):
        calls.append(path)
        return {'release_ready': False, 'publication_blocked': True}
    monkeypatch.setattr(module, 'build_candidate', probe, raising=False)
    assert module.main(['--work', str(work), '--build']) == 0
    assert calls == [work]
    assert not work.exists()


def test_candidate_report_cannot_claim_release_clearance(tmp_path, monkeypatch):
    module = builder()
    monkeypatch.setattr(module, 'build_candidate', lambda work: {'release_ready': True, 'publication_blocked': False})
    with pytest.raises(ValueError, match='publication'):
        module.main(['--work', str(tmp_path / 'fresh'), '--build'])


def test_build_candidate_rejects_unsupported_host_before_writes(tmp_path, monkeypatch):
    module = builder()
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    work = tmp_path / 'fresh'
    with pytest.raises(RuntimeError, match='macOS arm64'):
        module.build_candidate(work)
    assert not work.exists()


def test_build_candidate_rejects_existing_workspace(tmp_path):
    module = builder()
    with pytest.raises(ValueError, match='fresh'):
        module.build_candidate(tmp_path)


def test_build_candidate_rejects_shell_paths_before_writes(tmp_path):
    module = builder()
    work = tmp_path / 'unsafe workspace'
    with pytest.raises(ValueError, match='metacharacters'):
        module.build_candidate(work)
    assert not work.exists()
