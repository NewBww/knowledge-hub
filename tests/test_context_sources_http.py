from fastapi.testclient import TestClient
from knowledge_hub.http import create_app


def test_production_factory_context_routes_human_only_and_restart(tmp_path):
    root = tmp_path / 'selected'
    root.mkdir()
    (root / 'note.txt').write_text('Synthetic needle evidence')
    app = create_app(tmp_path / 'data', 'human-test-token', 'agent-test-token')
    with TestClient(app) as client:
        assert client.get('/api/context-sources').status_code == 401
        assert client.get('/api/context-sources', headers={'Authorization': 'Bearer agent-test-token'}).status_code == 403
        assert client.post('/api/session', headers={'Authorization': 'Bearer human-test-token'}).status_code == 200
        assert client.get('/api/context-sources').json() == {'sources': []}
        source = app.state.context_sources.register_selected([root])[0]
        base = '/api/context-sources/' + source['id']
        assert client.get(base).json() == source
        assert client.post(base + '/list', json={'relative_path': ''}).json()['entries'][0]['name'] == 'note.txt'
        assert client.post(base + '/read', json={'relative_path': 'note.txt'}).json()['text'] == 'Synthetic needle evidence'
        assert client.post(base + '/search', json={'query': 'needle'}).json()['matches'][0]['line'] == 1
        assert client.post(base + '/read', json={'relative_path': '../outside'}).status_code == 400
        assert client.post(base + '/read', json={'relative_path': 'note.txt', 'path': '/etc/passwd'}).status_code == 422
        assert client.post('/api/context-sources', json={'path': str(root)}).status_code == 405
        assert client.post(base + '/revoke', json={}).json()['status'] == 'revoked'
        assert client.post(base + '/read', json={'relative_path': 'note.txt'}).status_code == 403
    restarted = create_app(tmp_path / 'data', 'human-test-token', 'agent-test-token')
    assert restarted.state.context_sources.get(source['id'])['status'] == 'revoked'


def test_agent_cannot_read_or_revoke_native_grant(tmp_path):
    app = create_app(tmp_path / 'data', 'human', 'agent')
    selected = tmp_path / 'evidence.txt'
    selected.write_text('private synthetic evidence')
    source = app.state.context_sources.register_selected([selected])[0]
    with TestClient(app) as client:
        for suffix in ['read', 'search', 'list', 'revoke']:
            response = client.post('/api/context-sources/' + source['id'] + '/' + suffix,
                                   json={'relative_path': '', 'query': 'evidence'},
                                   headers={'Authorization': 'Bearer agent'})
            assert response.status_code == 403
    assert app.state.context_sources.get(source['id'])['status'] == 'active'
