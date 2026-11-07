import pytest
from fastapi.testclient import TestClient
from knowledge_hub.http import create_app


def app_client(tmp_path):
    app = create_app(tmp_path, 'human', 'agent')
    client = TestClient(app)
    assert client.post('/api/session', headers={'authorization': 'Bearer human'}).status_code == 200
    return client


def test_registered_queue_access_and_human_authorization(tmp_path):
    client = app_client(tmp_path)
    path = '/api/captures'
    agent = {'authorization': 'Bearer agent'}
    assert client.get('/api/curator/settings').status_code == 404
    assert client.get('/api/agent/access').json()['enabled'] is False
    assert client.get(path, headers=agent).status_code == 403
    capture = client.post(path, json={'text': 'Synthetic paste'}).json()
    assert capture['status'] == 'pending_agent'
    assert 'project_id' not in capture
    assert client.get(path).json()['captures'][0]['id'] == capture['id']
    assert client.get(path + '/' + capture['id']).json()['text'] == 'Synthetic paste'
    assert client.get(path + '/' + capture['id'], headers=agent).status_code == 403
    assert client.post('/api/agent/access', json={'enabled': True}, headers=agent).status_code == 403
    assert client.get('/api/agent/access').json()['enabled'] is False
    assert client.post('/api/agent/access', json={'enabled': True}).json()['enabled'] is True
    assert client.get(path, headers=agent).json()['total'] == 1
    detail = client.get(path + '/' + capture['id'], headers=agent)
    assert detail.json()['text'] == 'Synthetic paste'
    assert 'project_id' not in detail.text
    assert client.post(path, json={'text': 'agent source'}, headers=agent).status_code == 403
    assert client.delete(path + '/' + capture['id'], headers=agent).status_code == 403
    assert client.post(path + '/' + capture['id'] + '/finish', json={'retain_source': False}, headers=agent).status_code == 403
    assert client.post(path + '/' + capture['id'] + '/curate', json={}).status_code == 404
    assert client.post('/api/agent/access', json={'enabled': False}).json()['enabled'] is False
    assert client.get(path, headers=agent).status_code == 403
    assert client.get(path + '/' + capture['id'], headers=agent).status_code == 403
    assert client.post(path + '/' + capture['id'] + '/finish', json={'retain_source': False}).json()['status'] == 'deleted'
    assert client.get(path + '/' + capture['id']).status_code == 404


def test_http_bounds_and_sanitized_errors(tmp_path):
    client = app_client(tmp_path)
    path = '/api/captures'
    assert client.post(path, json={'text': ''}).status_code == 422
    response = client.post(path, json={'files': [{'name': 'file.txt', 'media_type': 'text/plain', 'content_base64': 'NOT A BASE64 SECRET'}]})
    assert response.status_code == 422
    assert 'SECRET' not in response.text
    assert client.post(path, json={'text': 'x' * 100001}).status_code == 422
    assert client.post(path, content=b'{}', headers={'content-length': str(30 * 1024 * 1024)}).status_code == 413
