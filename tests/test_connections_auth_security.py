"""Synthetic auth/config security regressions; no remote authentication."""
import threading
from urllib.parse import parse_qs, urlparse

import pytest
from knowledge_hub.connections import Connections, configuration
from knowledge_hub.core import DomainError
from knowledge_hub.store import Store


class Vault:
    def __init__(self):
        self.value = None
    def put(self, name, value):
        self.value = value
    def get(self, name):
        return self.value


def configured(root):
    result = Connections(Store(root), vault=Vault(), discover=lambda name: '/synthetic/' + name)
    result.confirm({'connection': 'openrouter', 'model': 'synthetic/model'}, consent=True, human=True)
    return result


def start(connections):
    handoff = connections.start_auth('openrouter', human=True, callback_url='http://127.0.0.1:8765/curator-auth/callback')
    return parse_qs(urlparse(handoff['url']).query)['state'][0]


def test_generation_rotates_on_confirm_and_key_replacement_but_not_stage(tmp_path):
    connections = configured(tmp_path)
    first = connections.state()['generation']
    assert isinstance(first, str) and first
    connections.stage({'connection': 'gemini', 'model': 'gemini-2.5-pro'})
    assert connections.state()['generation'] == first
    connections.confirm({'connection': 'openrouter', 'model': 'synthetic/model'}, consent=True, human=True)
    second = connections.state()['generation']
    assert second != first
    connections.set_key('openrouter', 'synthetic-key', human=True)
    assert connections.state()['generation'] not in {first, second}
    assert connections.state()['enabled'] is False
    assert connections.state()['status'] == 'unchecked'


@pytest.mark.parametrize('replacement', ['same_confirm', 'model_confirm', 'provider_confirm', 'key'])
def test_pending_pkce_is_invalid_after_confirm_or_key_replacement(tmp_path, replacement):
    connections = configured(tmp_path)
    state = start(connections)
    exchanges = []
    connections.exchange = lambda *args: exchanges.append(args) or {'key': 'old-auth-key'}
    if replacement == 'key':
        connections.set_key('openrouter', 'replacement-key', human=True)
    else:
        connection = 'gemini' if replacement == 'provider_confirm' else 'openrouter'
        model = 'synthetic/other-model' if replacement == 'model_confirm' else 'synthetic/model'
        connections.confirm({'connection': connection, 'model': model}, consent=True, human=True)
    with pytest.raises(DomainError, match='invalid_auth_state'):
        connections.complete_auth(state, 'synthetic-code', human=True)
    assert exchanges == []
    assert connections.vault.value != 'old-auth-key'


def test_pending_pkce_generation_is_bound_across_connection_instances(tmp_path):
    connections = configured(tmp_path)
    state = start(connections)
    second = Connections(connections.store, vault=connections.vault)
    second.confirm({'connection': 'openrouter', 'model': 'synthetic/model'}, consent=True, human=True)
    connections.exchange = lambda *args: pytest.fail('stale code must not be exchanged')
    with pytest.raises(DomainError, match='invalid_auth_state'):
        connections.complete_auth(state, 'synthetic-code', human=True)


def test_pkce_exchange_cannot_replace_a_newer_key(tmp_path):
    connections = configured(tmp_path)
    state = start(connections)
    entered, release = threading.Event(), threading.Event()
    def exchange(*args):
        entered.set()
        assert release.wait(5)
        return {'key': 'old-exchange-key'}
    connections.exchange = exchange
    errors = []
    def complete():
        try:
            connections.complete_auth(state, 'synthetic-code', human=True)
        except DomainError as error:
            errors.append(error.code)
    worker = threading.Thread(target=complete)
    worker.start()
    try:
        assert entered.wait(5)
        connections.set_key('openrouter', 'replacement-key', human=True)
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert errors == ['invalid_auth_state']
    assert connections.vault.value == 'replacement-key'


@pytest.mark.parametrize('model', ['auto', 'default', 'latest', 'openrouter/auto',
    'openrouter/default', 'provider/latest', 'openrouter/openrouter/auto', 'provider/model:latest'])
def test_model_route_alias_segments_are_rejected(model):
    for provider in ['openrouter', 'opencode']:
        with pytest.raises(DomainError, match='invalid_configuration'):
            configuration({'connection': provider, 'model': model})


@pytest.mark.parametrize('model', ['openrouter/autoencoder-v2', 'provider/default-v3',
    'provider/latest-research-2026', 'provider/automatic', 'provider/model-2026-11-05'])
def test_explicit_model_names_containing_alias_substrings_are_allowed(model):
    assert configuration({'connection': 'openrouter', 'model': model})['model'] == model


@pytest.mark.parametrize('location', ['ancestor', 'config'])
def test_handoff_rejects_symlinked_profile_ancestors_and_configuration(tmp_path, location):
    from knowledge_hub.cli_auth import auth_handoff
    root, external = tmp_path / 'app', tmp_path / 'external'
    root.mkdir(); external.mkdir()
    if location == 'ancestor':
        (root / 'linked').symlink_to(external, target_is_directory=True)
        root = root / 'linked' / 'app'
    else:
        home = root / 'curator-clients/gemini'
        home.mkdir(parents=True)
        (home / 'config').symlink_to(external, target_is_directory=True)
    with pytest.raises(DomainError, match='unsafe_local_storage'):
        auth_handoff(root, 'gemini', '/must/not/execute', 'https://geminicli.com/', ['gemini'])
    assert list(external.iterdir()) == []


def test_gemini_runtime_rejects_symlinked_config_before_launch(tmp_path, monkeypatch):
    from knowledge_hub import cli_models
    home, external = tmp_path / 'curator-clients/gemini', tmp_path / 'external'
    home.mkdir(parents=True); external.mkdir()
    (home / 'config').symlink_to(external, target_is_directory=True)
    launches = []
    def process(*args, **kwargs):
        launches.append(args)
        raise DomainError('should_not_launch')
    monkeypatch.setattr(cli_models, '_run_process', process)
    with pytest.raises(DomainError, match='unsafe_local_storage'):
        cli_models.GeminiAdapter(tmp_path, executable='/synthetic/gemini').complete(
            'gemini-2.5-pro', {'text': 'Synthetic'}, threading.Event())
    assert launches == []
    assert list(external.iterdir()) == []
