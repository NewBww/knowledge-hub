from fastapi.testclient import TestClient
import pytest
from knowledge_hub.http import create_app


def client(tmp_path):
    return TestClient(create_app(tmp_path, 'human-secret', 'agent-secret'))


def test_health_authentication_and_shared_workspace_discovery(tmp_path):
    c = client(tmp_path)
    assert c.get('/api/health').json() == {'status': 'ok', 'version': '0.3.0'}
    assert c.get('/api/workspace').status_code == 401
    assert c.post('/api/changes', json={}).status_code == 401
    headers = {'Authorization': 'Bearer agent-secret'}
    state = c.get('/api/workspace', headers=headers).json()
    assert state['revision'] == 0
    assert state['item_count'] == state['book_count'] == 0
    assert c.get('/api/warehouse', headers=headers).json() == {'items': [], 'total': 0}
    assert c.post('/api/projects', headers=headers, json={'name': 'No partitions'}).status_code == 410
    assert c.get('/api/workspace', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert c.get('/api/workspace', headers={b'authorization': b'Bearer \xff'}).status_code == 401


def test_human_bootstrap_cookie_not_ambient_login(tmp_path):
    c = client(tmp_path)
    c.get('/')
    assert c.get('/api/workspace').status_code == 401
    assert c.post('/api/session').status_code == 401
    assert c.post('/api/session', headers={'Authorization': 'Bearer agent-secret'}).status_code == 401
    response = c.post('/api/session', headers={'Authorization': 'Bearer human-secret'})
    assert response.status_code == 200
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie
    assert 'human-secret' not in cookie
    assert c.get('/api/workspace').json()['item_count'] == 0
    assert c.post('/api/agent/access', json={'enabled': True}).status_code == 200


def test_loopback_host_and_exact_origin_state_change_policy(tmp_path):
    c = client(tmp_path)
    headers = {'Authorization': 'Bearer agent-secret'}
    payload = {'base_revision': 0, 'idempotency_key': 'origin-test', 'summary': 'Synthetic',
               'operations': [{'op': 'upsert', 'title': 'Synthetic', 'body': 'Synthetic', 'kind': 'fact'}]}
    assert c.get('/api/health', headers={'Host': 'evil.example'}).status_code == 400
    assert c.get('/api/health', headers={'Host': '127.0.0.1.evil.example'}).status_code == 400
    assert c.post('/api/changes', headers={**headers, 'Origin': 'http://evil.example'}, json=payload).status_code == 403
    assert c.post('/api/session', headers={'Authorization': 'Bearer human-secret', 'Origin': 'null'}).status_code == 403
    assert c.post('/api/changes', headers={**headers, 'Origin': 'http://testserver'}, json=payload).status_code == 200
    local = TestClient(create_app(tmp_path / 'local', 'human-secret', 'agent-secret'), base_url='http://127.0.0.1:8123')
    assert local.post('/api/session', headers={'Authorization': 'Bearer human-secret', 'Origin': 'http://127.0.0.1:8123'}).status_code == 200
    assert local.post('/api/changes', headers={'Origin': 'http://127.0.0.1:9999'}, json=payload).status_code == 403


def test_http_propose_human_review_and_shared_readback(tmp_path):
    agent = client(tmp_path)
    headers = {'Authorization': 'Bearer agent-secret'}
    payload = {'base_revision': 0, 'idempotency_key': 'first', 'summary': 'Synthetic only', 'operations': [
        {'op': 'upsert', 'title': 'Synthetic apple', 'body': '<script>inert</script>', 'kind': 'fact'}]}
    response = agent.post('/api/changes', headers=headers, json=payload)
    assert response.status_code == 200
    change = response.json()
    assert agent.get('/api/warehouse', headers=headers).json() == {'items': [], 'total': 0}
    assert agent.get('/api/changes', headers=headers).json() == {'changes': [change]}
    approval = f"/api/changes/{change['id']}/approve"
    assert agent.post(approval, headers=headers).status_code == 403
    assert agent.post(approval, headers={'Authorization': 'Bearer human-secret'}).status_code == 401
    assert agent.post('/api/changes', headers=headers, json={**payload, 'approved': True}).status_code == 422
    human = client(tmp_path)
    human.post('/api/session', headers={'Authorization': 'Bearer human-secret'})
    assert human.post(approval, headers=headers).status_code == 403
    assert human.post(approval).json()['result_revision'] == 1
    identifier = change['operations'][0]['id']
    item = agent.get(f'/api/warehouse/{identifier}', headers=headers).json()
    assert item['body'] == '<script>inert</script>'
    assert 'project_id' not in item
    assert agent.get('/api/warehouse?q=apple&state=current', headers=headers).json() == {'items': [item], 'total': 1}
    state = agent.get('/api/workspace', headers=headers).json()
    assert state['revision'] == state['item_count'] == 1
    assert agent.get('/api/warehouse').status_code == 401
    assert agent.get('/api/warehouse/missing', headers=headers).status_code == 404
    pending = human.post('/api/changes', json={**payload, 'base_revision': 1, 'idempotency_key': 'reject'}).json()
    rejection = f"/api/changes/{pending['id']}/reject"
    assert agent.post(rejection, headers=headers).status_code == 403
    assert human.post(rejection).json()['status'] == 'rejected'
    assert agent.get('/api/warehouse', headers=headers).json() == {'items': [item], 'total': 1}
    assert agent.get('/api/workspace', headers=headers).json()['revision'] == 1


def test_static_reader_served_without_api_login(tmp_path, monkeypatch):
    import knowledge_hub.http as module
    web = tmp_path / 'fixture-web'
    web.mkdir()
    (web / 'index.html').write_text('<!doctype html><title>Synthetic reader</title>')
    (web / 'app.js').write_text('/* synthetic */')
    (web / 'styles.css').write_text('/* synthetic */')
    monkeypatch.setattr(module, 'WEB_DIR', web)
    c = client(tmp_path / 'data')
    assert c.get('/').status_code == 200
    assert 'Synthetic reader' in c.get('/').text
    assert c.get('/assets/app.js').status_code == 200
    assert c.get('/assets/styles.css').status_code == 200
    assert c.get('/assets/../knowledge.sqlite3').status_code == 404
    assert c.get('/api/workspace').status_code == 401
    assert c.get('/').headers['referrer-policy'] == 'no-referrer'
    assert "default-src 'self'" in c.get('/').headers['content-security-policy']


@pytest.mark.parametrize('human,agent', [('', 'agent'), ('human', ''), ('same', 'same')])
def test_invalid_role_secrets_refused_before_database_creation(tmp_path, human, agent):
    with pytest.raises(ValueError, match='distinct_nonempty_tokens'):
        create_app(tmp_path, human, agent)
    assert not (tmp_path / 'knowledge.sqlite3').exists()
