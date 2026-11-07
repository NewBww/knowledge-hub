from uuid import uuid4
from fastapi.testclient import TestClient
from knowledge_hub.http import create_app
from test_library import setup, command


def test_http_reader_and_human_review_boundary(tmp_path):
    store, p, item = setup(tmp_path)
    app = create_app(tmp_path, 'synthetic-human', 'synthetic-agent')
    with TestClient(app) as human, TestClient(app) as agent:
        agent.headers['Authorization'] = 'Bearer synthetic-agent'
        root = '/api/library'
        assert human.get(root + '/books').status_code == 401
        assert human.post('/api/session', headers={'Authorization': 'Bearer synthetic-human'}).status_code == 200
        assert human.get(root + '/books').json() == {'books': []}
        cmd = command(item)
        response = agent.post(root + '/changes', json=cmd)
        assert response.status_code == 200, response.text
        pending = response.json()
        url = root + '/changes/' + pending['id']
        assert agent.post(url + '/approve').status_code == 403
        assert agent.post(url + '/reject').status_code == 403
        assert human.get(root + '/books').json() == {'books': []}
        assert human.post(url + '/approve').status_code == 200
        book = human.get(root + '/books').json()['books'][0]
        detail = agent.get(root + '/books/' + book['id']).json()
        page = agent.get(root + '/pages/' + cmd['operations'][0]['id']).json()
        assert detail['pages'][0] == page
        assert page['sections'][0]['body'] == 'Explanation'
        assert 'body' not in page['sections'][0]['supports'][0]
        assert human.get(root + '/changes').json()['changes'][0]['status'] == 'approved'
        assert human.get(root + '/books/' + str(uuid4())).status_code == 404
        assert human.get(root + '/pages/' + str(uuid4())).status_code == 404
        # Existing full canonical endpoint remains usable.
        assert human.get('/api/warehouse/' + item).json()['body'] == 'Canonical only'
        cmd['unexpected'] = True
        assert human.post(root + '/changes', json=cmd).status_code == 422
        old_cookie = human.cookies.get('kh_session')
    restarted = create_app(tmp_path, 'synthetic-human', 'synthetic-agent')
    with TestClient(restarted) as reader:
        reader.cookies.set('kh_session', old_cookie)
        assert reader.get('/api/workspace').status_code == 401
        reader.cookies.clear()
        assert reader.post('/api/session', headers={'Authorization': 'Bearer synthetic-human'}).status_code == 200
        assert reader.get(root + '/books/' + book['id']).json() == detail
        assert reader.get(root + '/pages/' + cmd['operations'][0]['id']).json() == page
        assert reader.get('/api/warehouse/' + item).json()['body'] == 'Canonical only'
        assert reader.get(root + '/changes').json()['changes'][0]['status'] == 'approved'
