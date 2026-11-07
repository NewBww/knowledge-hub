import stat
from knowledge_hub.cli import resolve_data_dir, load_agent_token


def test_data_dir_and_persistent_private_agent_token(tmp_path, monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_HUB_DATA_DIR', str(tmp_path / 'configured'))
    assert resolve_data_dir() == tmp_path / 'configured'
    assert resolve_data_dir(tmp_path) == tmp_path
    token = load_agent_token(tmp_path)
    assert len(token) >= 32
    assert load_agent_token(tmp_path) == token
    assert (tmp_path / 'agent.token').read_text() == token
    assert stat.S_IMODE((tmp_path / 'agent.token').stat().st_mode) == 0o600
    assert not (tmp_path / 'knowledge.sqlite3').exists()


def test_invalid_token_symlink_refused(tmp_path):
    import pytest
    target = tmp_path / 'other-secret'
    target.write_text('a' * 40)
    (tmp_path / 'agent.token').symlink_to(target)
    with pytest.raises(ValueError, match='symbolic link'):
        load_agent_token(tmp_path)
    assert target.read_text() == 'a' * 40



def test_default_cli_delegates_to_desktop_without_browser(tmp_path, monkeypatch):
    import knowledge_hub.desktop as desktop
    from knowledge_hub.cli import main
    seen = []
    monkeypatch.setattr(desktop, 'launch', lambda data_dir=None: seen.append(data_dir))
    main(['--data-dir', str(tmp_path)])
    main(['desktop', '--data-dir', str(tmp_path)])
    assert seen == [tmp_path, tmp_path]


def test_frozen_worker_dispatch_precedes_gui_startup(tmp_path, monkeypatch):
    import multiprocessing
    import knowledge_hub.desktop as desktop
    from knowledge_hub.cli import main
    seen = []
    monkeypatch.setattr(multiprocessing, 'freeze_support', lambda: seen.append('workers'))
    monkeypatch.setattr(desktop, 'launch', lambda data_dir=None: seen.append('gui'))
    main(['desktop', '--data-dir', str(tmp_path)])
    assert seen == ['workers', 'gui']

