"""Manual update UI/API never invents a latest release without a configured feed."""
from fastapi.testclient import TestClient
from knowledge_hub.http import create_app


def test_update_state_requires_human_and_reports_unconfigured_source(tmp_path):
    app = create_app(tmp_path, 'synthetic-human', 'synthetic-agent')
    with TestClient(app) as client:
        assert client.get('/api/updates').status_code == 401
        headers = {'Authorization': 'Bearer synthetic-agent'}
        assert client.get('/api/updates', headers=headers).status_code == 403
        assert client.post('/api/updates/check', headers=headers).status_code == 403
        assert client.post('/api/session', headers={'Authorization': 'Bearer synthetic-human'}).status_code == 200
        result = client.get('/api/updates')
        assert result.status_code == 200, result.text
        state = result.json()
        assert state['current_version'] == app.version
        assert state['status'] == 'unconfigured' and state['configured'] is False
        assert 'latest_version' not in state
        assert client.post('/api/updates/check').json() == state
        blocked = client.post('/api/updates/install')
        assert blocked.status_code == 409
        assert blocked.json() == {'error': 'update_source_unconfigured'}
        assert client.post('/api/updates/check', json={'url': 'https://untrusted.invalid/app'}).status_code == 422


def test_configured_native_check_is_human_only_and_install_requires_native_confirmation(tmp_path):
    from knowledge_hub.updater import Updater

    class NativeBoundary:
        calls = 0

        def check_for_updates(self):
            self.calls += 1

    native = NativeBoundary()
    app = create_app(tmp_path, 'synthetic-human', 'synthetic-agent')
    app.state.updater = Updater(app.version, native=native)
    with TestClient(app) as client:
        agent = {'Authorization': 'Bearer synthetic-agent'}
        assert client.post('/api/updates/check', headers=agent).status_code == 403
        assert native.calls == 0
        assert client.post('/api/session', headers={'Authorization': 'Bearer synthetic-human'}).status_code == 200
        state = client.get('/api/updates').json()
        assert state['configured'] is True and state['status'] == 'ready'
        assert native.calls == 0
        assert client.post('/api/updates/check', json={'url': 'https://untrusted.invalid/app'}).status_code == 422
        assert native.calls == 0
        response = client.post('/api/updates/check')
        assert response.status_code == 200
        assert response.json()['status'] == 'native_dialog'
        assert 'latest_version' not in response.json()
        assert native.calls == 1
        install = client.post('/api/updates/install')
        assert install.status_code == 409
        assert install.json() == {'error': 'native_confirmation_required'}
        assert native.calls == 1
