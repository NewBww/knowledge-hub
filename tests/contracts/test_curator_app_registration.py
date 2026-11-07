"""Exercise production app registration, without fixture-side route wiring."""
from fastapi.testclient import TestClient
from knowledge_hub.http import create_app


def test_production_app_exposes_curator_and_protects_human_configuration(tmp_path):
    app = create_app(tmp_path, 'synthetic-human-token', 'synthetic-agent-token')
    with TestClient(app) as client:
        assert client.get('/api/curator').status_code == 401
        agent = {'Authorization': 'Bearer synthetic-agent-token'}
        catalog = client.get('/api/curator/catalog', headers=agent)
        assert catalog.status_code == 200
        assert {entry['id'] for entry in catalog.json()['connections']} == {
            'chatgpt', 'copilot', 'openrouter', 'opencode', 'gemini', 'hermes'}
        command = {'configuration': {'connection': 'openrouter', 'model': 'synthetic/model'},
                   'confirm': True, 'consent': True}
        assert client.post('/api/curator/config', json=command, headers=agent).status_code == 403
        assert client.post('/api/session', headers={'Authorization': 'Bearer synthetic-human-token'}).status_code == 200
        result = client.post('/api/curator/config', json=command)
        assert result.status_code == 200
        state = client.get('/api/curator').json()
        assert state['connection'] == 'openrouter'
        assert state['model'] == 'synthetic/model'
        assert state['enabled'] is False
        assert app.state.runtime is app.state.curator_runtime
