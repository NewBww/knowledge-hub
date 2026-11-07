"""Human handoffs through the production app, without client execution."""
import shlex

import pytest
from fastapi.testclient import TestClient
from knowledge_hub.http import create_app


def test_catalog_consent_discloses_underlying_destinations_and_retention_exceptions(tmp_path):
    app = create_app(tmp_path, 'synthetic-human', 'synthetic-agent')
    disclosure = app.state.connections.catalog()['disclosure']
    assert 'underlying provider' in disclosure
    assert 'account privacy settings' in disclosure
    assert 'safety/legal retention exceptions' in disclosure
    assert 'task/session traces' in disclosure


@pytest.mark.parametrize('provider', ['chatgpt', 'copilot', 'opencode', 'gemini', 'hermes'])
def test_production_auth_handoff_is_a_complete_shell_quoted_profile_script(tmp_path, provider, monkeypatch):
    root = tmp_path / "Synthetic space's $(not-a-command) <tag>"
    app = create_app(root, 'synthetic-human', 'synthetic-agent')
    app.state.connections.discover = lambda name: '/synthetic bin/' + name
    monkeypatch.setenv('SYNTHETIC_PRIVATE_KEY', 'never-display-this-secret')
    client = TestClient(app)
    assert client.post('/api/session', headers={'Authorization': 'Bearer synthetic-human'}).status_code == 200
    result = client.post('/api/curator/auth/start', json={'connection': provider})
    assert result.status_code == 200, result.text
    handoff = result.json()
    assert shlex.split(handoff['cwd_command']) == ['cd', '--', handoff['cwd']]
    assert handoff['automatic_execution'] is False
    assert handoff['readiness'] == 'not_checked'
    for text, argv in zip(handoff['display_commands'], handoff['steps'], strict=True):
        assert shlex.split(text) == argv
        assert argv[:2] == ['env', '-i']
        assert 'HOME=' + handoff['cwd'] in argv
    assert 'never-display-this-secret' not in result.text
    assert not list(root.rglob('auth.json'))
    from knowledge_hub.connections import PRESETS
    assert PRESETS[provider][3] == handoff['command']
    assert 'Hermes' not in handoff['reason'] if provider != 'hermes' else 'Nous' in handoff['reason']
    assert app.state.connections.state()['enabled'] is False
    if provider == 'copilot':
        assert handoff['environment']['HOME'] == str(root / 'cli-auth/copilot')
        assert handoff['environment']['COPILOT_HOME'] == str(root / 'cli-auth/copilot/.copilot')
        assert handoff['command'] == ['copilot', 'login']
    elif provider == 'opencode':
        assert handoff['environment']['HOME'] == str(root / 'cli-auth/opencode')
        assert handoff['environment']['XDG_DATA_HOME'] == str(root / 'cli-auth/opencode/data')
        assert handoff['command'] == ['opencode', 'auth', 'login']
    elif provider == 'hermes':
        assert handoff['command'] == ['hermes', 'portal']
        assert len(handoff['steps']) == 2
        assert handoff['steps'][1][-7:-1] == ['start', '--provider', 'nous', '--host', '127.0.0.1', '--port']
    elif provider == 'chatgpt':
        assert handoff['execution'] == 'blocked_tool_denial_unverified'
