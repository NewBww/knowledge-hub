from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from knowledge_hub.connections import Connections
from knowledge_hub.connections_http import register
from knowledge_hub.core import DomainError
from knowledge_hub.store import Store
from test_connection_profiles import Vault


def test_profile_http_requires_human_binds_keys_and_pins_discovered_models(tmp_path):
    app = FastAPI()
    @app.middleware('http')
    async def auth(request: Request, call_next):
        request.state.human = request.headers.get('x-synthetic-human') == 'yes'
        return await call_next(request)
    @app.exception_handler(DomainError)
    async def error(request, exc): return JSONResponse({'error': exc.code}, status_code=exc.status)
    c = Connections(Store(tmp_path), vault=Vault())
    register(app, c.store, connections=c)
    client = TestClient(app, base_url='http://localhost:54321')
    human = {'x-synthetic-human': 'yes'}
    payload = {'auth_route': 'openrouter_api_key', 'name': 'Account'}
    assert client.post('/api/curator/profiles', json=payload).status_code == 403
    response = client.post('/api/curator/profiles', json=payload, headers=human)
    assert response.status_code == 200
    profile = response.json(); identifier = profile['profile_id']
    assert client.get('/api/curator/profiles').json()['active_profile_id'] == identifier
    assert client.post('/api/curator/profiles/key', json={'profile_id': identifier, 'key': 'SYNTHETIC'}, headers=human).status_code == 200
    c.model_listing = lambda *args: {'source': 'synthetic', 'availability': 'catalog_not_verified', 'models': [{'id': 'vendor/model', 'name': 'Model'}]}
    assert client.post('/api/curator/profiles/models', json={'profile_id': identifier}).status_code == 403
    assert client.post('/api/curator/profiles/models', json={'profile_id': identifier}, headers=human).json()['models'] == [{'id': 'vendor/model', 'name': 'Model'}]
    selected = client.post('/api/curator/profiles/model', json={'profile_id': identifier, 'model': 'vendor/model'}, headers=human)
    assert selected.status_code == 200 and selected.json()['model'] == 'vendor/model'
    assert not client.get('/api/curator').json()['enabled']
    other = client.post('/api/curator/profiles', json=payload, headers=human).json()
    stale = client.post('/api/curator/profiles/key', json={'profile_id': identifier, 'key': 'SYNTHETIC_WRONG_ACCOUNT'}, headers=human)
    assert stale.status_code == 409
    assert c._vault().get(c.credential_name(other['profile_id'])) is None
    assert client.post('/api/curator/profiles/activate', json={'profile_id': identifier}, headers=human).json()['profile_id'] == identifier
