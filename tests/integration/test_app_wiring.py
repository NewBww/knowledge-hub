"""Actual app-factory wiring, not a test-only router registration."""
from fastapi.testclient import TestClient
from knowledge_hub.http import create_app


def test_app_factory_registers_library_and_human_capture_routes(tmp_path):
    app = create_app(tmp_path, 'synthetic-human', 'synthetic-agent')
    with TestClient(app) as client:
        assert client.post('/api/session', headers={'Authorization': 'Bearer synthetic-human'}).status_code == 200
        assert client.get('/api/workspace').json()['item_count'] == 0
        books = client.get('/api/library/books')
        assert books.status_code == 200, books.text
        assert books.json() == {'books': []}
        capture = client.post('/api/captures', json={'text': 'A synthetic finding for the external agent.'})
        assert capture.status_code == 200, capture.text
        assert capture.json()['status'] == 'pending_agent'
        access = client.get('/api/agent/access')
        assert access.status_code == 200, access.text
        denied = client.post('/api/agent/access', headers={'Authorization': 'Bearer synthetic-agent'}, json={'enabled': True})
        assert denied.status_code == 403
        assert denied.json()['error'] == 'approval_required'
        assert client.get('/api/warehouse').json()['total'] == 0
