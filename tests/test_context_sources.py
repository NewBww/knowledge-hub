"""Synthetic local grants only; never discover the owner's filesystem."""
from pathlib import Path
import pytest
from knowledge_hub.core import DomainError


def test_registration_is_opaque_read_only_and_persistent(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    root = tmp_path / 'selected'
    root.mkdir()
    (root / 'note.txt').write_text('Synthetic evidence')
    service = ContextSources(tmp_path / 'data')
    source = service.register_selected([root])[0]
    assert set(source) == {'id', 'kind', 'name', 'status'}
    assert source['kind'] == 'directory' and source['status'] == 'active'
    assert source['name'] == 'selected' and '/' not in source['id']
    restarted = ContextSources(tmp_path / 'data')
    assert restarted.sources() == [source]
    assert restarted.read(source['id'], 'note.txt')['text'] == 'Synthetic evidence'
    assert restarted.read(source['id'], 'note.txt')['trust'] == 'untrusted'
    assert str(root) not in str(restarted.sources())


@pytest.mark.parametrize('relative', ['../outside.txt', '/etc/passwd', 'a/../note.txt', 'a//note.txt', './note.txt', 'bad\\name', 'bad\x00name'])
def test_invalid_relative_paths_fail_closed(tmp_path, relative):
    from knowledge_hub.context_sources import ContextSources
    root = tmp_path / 'selected'
    root.mkdir()
    (root / 'note.txt').write_text('inside')
    (tmp_path / 'outside.txt').write_text('outside')
    service = ContextSources(tmp_path / 'data')
    source = service.register_selected([root])[0]
    with pytest.raises(DomainError):
        service.read(source['id'], relative)


def test_no_symlinks_root_replacement_or_special_files(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    import os
    root = tmp_path / 'selected'
    root.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('never disclose')
    (root / 'link.txt').symlink_to(outside)
    (root / 'nested').symlink_to(tmp_path, target_is_directory=True)
    os.mkfifo(root / 'fifo')
    service = ContextSources(tmp_path / 'data')
    source = service.register_selected([root])[0]
    for relative in ['link.txt', 'nested/outside.txt', 'fifo']:
        with pytest.raises(DomainError):
            service.read(source['id'], relative)
    with pytest.raises(DomainError):
        service.register_selected([root / 'link.txt'])
    root.rename(tmp_path / 'old')
    root.mkdir()
    (root / 'note.txt').write_text('replacement')
    with pytest.raises(DomainError):
        service.read(source['id'], 'note.txt')


def test_file_grants_are_exact_and_revoke_survives_restart(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    file = tmp_path / 'evidence.txt'
    file.write_text('exact file')
    service = ContextSources(tmp_path / 'data')
    source = service.register_selected([file])[0]
    assert service.read(source['id'])['text'] == 'exact file'
    with pytest.raises(DomainError):
        service.read(source['id'], 'sibling.txt')
    assert service.revoke(source['id'])['status'] == 'revoked'
    restarted = ContextSources(tmp_path / 'data')
    assert restarted.get(source['id'])['status'] == 'revoked'
    with pytest.raises(DomainError):
        restarted.read(source['id'])


def test_sensitive_and_generated_paths_never_exposed(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    root = tmp_path / 'selected'
    root.mkdir()
    blocked = ['.env', '.env.local', 'private.pem', 'credentials.json', 'id_rsa', 'token.key', '.git/config', 'node_modules/pkg.txt', 'dist/output.txt', 'thing.app/Contents/file.txt', 'local.sqlite3']
    for relative in blocked:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('secret sentinel')
    (root / 'readme.txt').write_text('public sentinel')
    service = ContextSources(tmp_path / 'data')
    source = service.register_selected([root])[0]
    for relative in blocked:
        with pytest.raises(DomainError):
            service.read(source['id'], relative)
        with pytest.raises(DomainError):
            service.register_selected([root / relative])
    assert [entry['name'] for entry in service.list(source['id'])['entries']] == ['readme.txt']
    assert 'secret sentinel' not in str(service.search(source['id'], 'sentinel'))


def test_gitignore_nested_negation_double_star_and_pruned_directories(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    root = tmp_path / 'selected'
    root.mkdir()
    (root / '.gitignore').write_text('*.log\n!keep.log\n/cache/\na/**/secret.txt\n/root-only.txt\n')
    for relative in ['drop.log', 'keep.log', 'cache/keep.log', 'a/secret.txt', 'a/b/secret.txt', 'root-only.txt', 'nested/root-only.txt', 'nested/hidden.txt', 'nested/ok.txt']:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('evidence')
    (root / 'nested/.gitignore').write_text('hidden.txt\n')
    service = ContextSources(tmp_path / 'data')
    source = service.register_selected([root])[0]
    for relative in ['drop.log', 'cache/keep.log', 'a/secret.txt', 'a/b/secret.txt', 'root-only.txt', 'nested/hidden.txt']:
        with pytest.raises(DomainError):
            service.read(source['id'], relative)
    for relative in ['keep.log', 'nested/root-only.txt', 'nested/ok.txt']:
        assert service.read(source['id'], relative)['text'] == 'evidence'


def test_operation_budgets_binary_rejection_and_search(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    root = tmp_path / 'selected'
    root.mkdir()
    (root / 'large.txt').write_text('x' * 100)
    (root / 'binary.dat').write_bytes(b'\x00binary')
    (root / 'unicode.txt').write_text('héllo\nneedle here\nneedle again')
    service = ContextSources(tmp_path / 'data', max_read_bytes=20, max_entries=2, max_search_bytes=80, max_results=1)
    source = service.register_selected([root])[0]
    read = service.read(source['id'], 'large.txt')
    assert len(read['text'].encode()) <= 20 and read['truncated']
    with pytest.raises(DomainError):
        service.read(source['id'], 'binary.dat')
    listing = service.list(source['id'])
    assert len(listing['entries']) <= 2 and listing['truncated']
    result = service.search(source['id'], 'needle', 'unicode.txt')
    assert len(result['matches']) == 1 and result['truncated']
    assert result['matches'][0]['line'] == 2
    assert result['trust'] == 'untrusted'


def test_revoke_during_read_discards_evidence(tmp_path, monkeypatch):
    from knowledge_hub.context_sources import ContextSources
    import os
    file = tmp_path / 'evidence.txt'
    file.write_text('must not escape after revoke')
    service = ContextSources(tmp_path / 'data')
    source = service.register_selected([file])[0]
    original = os.read
    def read_then_revoke(fd, count):
        result = original(fd, count)
        service.revoke(source['id'])
        return result
    monkeypatch.setattr(os, 'read', read_then_revoke)
    with pytest.raises(DomainError):
        service.read(source['id'])


def test_cross_process_revocation_and_private_metadata(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    import subprocess
    import sys
    import stat
    file = tmp_path / 'evidence.txt'
    file.write_text('synthetic')
    service = ContextSources(tmp_path / 'data')
    source = service.register_selected([file])[0]
    command = 'from pathlib import Path; from knowledge_hub.context_sources import ContextSources; import sys; ContextSources(Path(sys.argv[1])).revoke(sys.argv[2])'
    subprocess.run([sys.executable, '-c', command, str(tmp_path / 'data'), source['id']], check=True)
    assert service.get(source['id'])['status'] == 'revoked'
    with pytest.raises(DomainError):
        service.read(source['id'])
    assert stat.S_IMODE(service.database.stat().st_mode) == 0o600


def test_binary_search_still_consumes_global_byte_budget(tmp_path, monkeypatch):
    from knowledge_hub.context_sources import ContextSources
    import os
    root = tmp_path / 'selected'
    root.mkdir()
    for number in range(10):
        (root / f'{number}.bin').write_bytes(b'\x00' * 100)
    service = ContextSources(tmp_path / 'data', max_read_bytes=20, max_search_bytes=40)
    source = service.register_selected([root])[0]
    total = []
    read = os.read
    def measured(fd, count):
        result = read(fd, count)
        total.append(len(result))
        return result
    monkeypatch.setattr(os, 'read', measured)
    result = service.search(source['id'], 'absent')
    assert sum(total) <= 42
    assert result['truncated']
