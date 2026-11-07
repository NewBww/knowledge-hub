"""Synthetic saved account and authenticated discovery boundaries."""
import json
import pytest
from knowledge_hub.connections import Connections
from knowledge_hub.core import DomainError
from knowledge_hub.store import Store

class Vault:
    def __init__(self): self.values = {}
    def put(self, name, value): self.values[name] = value
    def get(self, name): return self.values.get(name)

def test_saved_accounts_are_independent_and_switch_revokes_readiness(tmp_path):
    vault = Vault()
    c = Connections(Store(tmp_path), vault=vault)
    with pytest.raises(DomainError, match='approval_required'):
        c.add_profile('openrouter_api_key', 'First')
    first = c.add_profile('openrouter_api_key', 'First', human=True)
    c.set_key('openrouter', 'SYNTHETIC_FIRST', human=True)
    second = c.add_profile('openrouter_api_key', 'Second', human=True)
    c.set_key('openrouter', 'SYNTHETIC_SECOND', human=True)
    assert first['profile_id'] != second['profile_id']
    assert vault.get(c.credential_name(first['profile_id'])) == 'SYNTHETIC_FIRST'
    assert vault.get(c.credential_name(second['profile_id'])) == 'SYNTHETIC_SECOND'
    selected = c.activate_profile(first['profile_id'], human=True)
    assert selected['profile_id'] == first['profile_id']
    assert selected['generation'] != first['generation']
    assert selected['enabled'] is False and selected['status'] != 'checked'
    restarted = Connections(Store(tmp_path), vault=vault)
    assert len(restarted.profiles()['profiles']) == 2
    assert restarted.state()['profile_id'] == first['profile_id']
    assert 'SYNTHETIC' not in json.dumps(restarted.profiles())
    assert 'SYNTHETIC' not in ''.join(p.read_text() for p in tmp_path.glob('*.json'))


def test_profile_key_requires_human_and_active_account_without_disclosing_secret(tmp_path):
    vault = Vault()
    c = Connections(Store(tmp_path), vault=vault)
    first = c.add_profile('openrouter_api_key', 'First', human=True)
    with pytest.raises(DomainError, match='approval_required'):
        c.set_profile_key(first['profile_id'], 'SYNTHETIC_PRIVATE_KEY')
    assert vault.values == {}
    result = c.set_profile_key(first['profile_id'], 'SYNTHETIC_PRIVATE_KEY', human=True)
    assert vault.get(c.credential_name(first['profile_id'])) == 'SYNTHETIC_PRIVATE_KEY'
    assert result['generation'] != first['generation']
    assert result['enabled'] is False and result['status'] == 'unchecked'
    assert 'SYNTHETIC_PRIVATE_KEY' not in json.dumps(result)
    assert 'SYNTHETIC_PRIVATE_KEY' not in c.path.read_text()
    second = c.add_profile('openrouter_api_key', 'Second', human=True)
    with pytest.raises(DomainError, match='configuration_changed'):
        c.set_profile_key(first['profile_id'], 'SYNTHETIC_WRONG_ACCOUNT', human=True)
    assert vault.get(c.credential_name(second['profile_id'])) is None
    assert vault.get(c.credential_name(first['profile_id'])) == 'SYNTHETIC_PRIVATE_KEY'


def test_routes_distinguish_native_cli_and_proxy_without_unsafe_handoffs(tmp_path):
    c = Connections(Store(tmp_path), vault=Vault(), discover=lambda name: '/synthetic/' + name)
    routes = {item['id']: item for item in c.catalog()['auth_routes']}
    assert {'chatgpt_oauth', 'codex_cli', 'hermes_agent_cli', 'nous_proxy', 'openrouter_api_key'} <= routes.keys()
    assert routes['hermes_agent_cli']['availability'] == 'unsupported_capability'
    first = c.add_profile('copilot_cli', 'One', human=True)
    handoff = c.start_profile_auth(first['profile_id'], human=True)
    assert first['profile_id'] in handoff['environment']['HOME']
    second = c.add_profile('copilot_cli', 'Two', human=True)
    assert c.start_profile_auth(second['profile_id'], human=True)['environment']['HOME'] != handoff['environment']['HOME']
    with pytest.raises(DomainError, match='configuration_changed'):
        c.start_profile_auth(first['profile_id'], human=True)
    blocked = c.add_profile('hermes_agent_cli', 'Blocked', human=True)
    with pytest.raises(DomainError, match='unsupported_capability'):
        c.start_profile_auth(blocked['profile_id'], human=True)


def test_legacy_key_ownership_survives_migration_without_keychain_read(tmp_path):
    vault = Vault()
    c = Connections(Store(tmp_path), vault=vault)
    c.confirm({'connection': 'openrouter', 'model': 'synthetic/legacy'}, consent=True, human=True)
    c.set_key('openrouter', 'SYNTHETIC_LEGACY', human=True)
    original_name = c.credential_name()
    added = c.add_profile('openrouter_api_key', 'Another', human=True)
    c.set_key('openrouter', 'SYNTHETIC_NEW', human=True)
    old = c.activate_profile('legacy', human=True)
    assert old['model'] == 'synthetic/legacy'
    assert c.credential_name() == original_name
    assert vault.get(original_name) == 'SYNTHETIC_LEGACY'
    assert vault.get(c.credential_name(added['profile_id'])) == 'SYNTHETIC_NEW'


def test_authenticated_model_listing_is_human_only_pinned_and_generation_bound(tmp_path):
    c = Connections(Store(tmp_path), vault=Vault())
    profile = c.add_profile('openrouter_api_key', 'Account', human=True)
    with pytest.raises(DomainError, match='approval_required'):
        c.discover_models(profile['profile_id'])
    with pytest.raises(DomainError, match='sign_in_required'):
        c.discover_models(profile['profile_id'], human=True)
    c.set_key('openrouter', 'SYNTHETIC', human=True)
    calls = []
    def listing(route, key, root):
        calls.append((route, key))
        return {'source': 'https://openrouter.ai/api/v1/models/user',
                'availability': 'account_filtered_not_inference_verified',
                'models': [{'id': 'synthetic/model', 'name': 'Synthetic model'}]}
    c.model_listing = listing
    result = c.discover_models(profile['profile_id'], human=True)
    assert calls == [('openrouter_api_key', 'SYNTHETIC')]
    assert result['models'][0]['name'] == 'Synthetic model'
    assert c.state()['model'] is None and c.state()['enabled'] is False
    with pytest.raises(DomainError, match='model_not_discovered'):
        c.select_model(profile['profile_id'], 'invented/model', human=True)
    selected = c.select_model(profile['profile_id'], 'synthetic/model', human=True)
    assert selected['model'] == 'synthetic/model' and not selected['enabled']
    c.set_key('openrouter', 'SYNTHETIC_REPLACEMENT', human=True)
    with pytest.raises(DomainError, match='model_discovery_required'):
        c.select_model(profile['profile_id'], 'synthetic/model', human=True)
