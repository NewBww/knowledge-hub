from fastapi.testclient import TestClient
from knowledge_hub.http import create_app


def test_shared_http_exposes_bounded_retrieval_without_project_selector(tmp_path):
    with TestClient(create_app(tmp_path, 'synthetic-human', 'synthetic-agent')) as client:
        client.headers['Authorization'] = 'Bearer synthetic-agent'
        for path in ['/api/agent/search', '/api/agent/context']:
            response = client.get(path, params={'max_chars': 1024})
            assert response.status_code == 200
            assert len(response.text) <= 1024
            invalid = client.get(path, params={'max_chars': 1023})
            assert invalid.status_code == 422
            assert invalid.json()['error'] == 'invalid_budget'
        invalid = client.get('/api/agent/knowledge/synthetic-missing', params={'max_chars': 0})
        assert invalid.status_code == 422
        assert invalid.json()['error'] == 'invalid_budget'
