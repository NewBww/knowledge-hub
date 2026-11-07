"""Project-free HTTP contract and fail-closed synthetic local capture."""
from fastapi.testclient import TestClient
from knowledge_hub.http import create_app


def clients(root):
    app = create_app(root, 'synthetic-human', 'synthetic-agent')
    human = TestClient(app)
    assert human.post('/api/session', headers={'Authorization': 'Bearer synthetic-human'}).status_code == 200
    agent = TestClient(app, headers={'Authorization': 'Bearer synthetic-agent'})
    return app, human, agent


def test_shared_http_empty_state_propose_and_human_review(tmp_path):
    app, human, agent = clients(tmp_path)
    workspace = human.get('/api/workspace')
    assert workspace.status_code == 200
    assert workspace.json()['item_count'] == 0
    assert human.get('/api/library/books').json() == {'books': []}
    assert human.get('/api/warehouse').json() == {'items': [], 'total': 0}
    proposal = dict(base_revision=0, idempotency_key='shared', summary='Synthetic', operations=[dict(op='upsert', title='Synthetic fact', body='Not private', kind='fact')])
    response = agent.post('/api/changes', json=proposal)
    assert response.status_code == 200
    change = response.json()
    assert 'project_id' not in response.text
    for action in ('approve', 'reject'):
        assert agent.post(f"/api/changes/{change['id']}/{action}").status_code == 403
    approved = human.post(f"/api/changes/{change['id']}/approve")
    assert approved.status_code == 200
    item_id = approved.json()['operations'][0]['id']
    assert human.get(f'/api/warehouse/{item_id}').json()['title'] == 'Synthetic fact'
    assert human.get('/api/warehouse', params={'q':'Synthetic', 'state':'current'}).json()['total'] == 1
    assert 'project_id' not in human.get('/api/changes').text
    assert agent.post('/api/agent/access', json={'enabled':True}).status_code == 403
    assert TestClient(app).get('/api/workspace').status_code == 401


def test_capture_global_consent_explicit_and_human_only_mutations(tmp_path):
    app, human, agent = clients(tmp_path)
    assert human.get('/api/agent/access').json()['enabled'] is False
    assert agent.get('/api/agent/access').json()['enabled'] is False
    capture = human.post('/api/captures', json={'text':'Synthetic local source','intent':'knowledge'})
    assert capture.status_code == 200, capture.text
    identifier = capture.json()['id']
    assert 'project_id' not in capture.text
    assert agent.get('/api/captures').status_code == 403
    assert agent.get(f'/api/captures/{identifier}').status_code == 403
    assert human.post('/api/agent/access', json={'enabled':True}).json()['enabled'] is True
    assert agent.get('/api/captures').json()['total'] == 1
    assert agent.get(f'/api/captures/{identifier}').json()['text'] == 'Synthetic local source'
    assert agent.delete(f'/api/captures/{identifier}').status_code == 403
    assert agent.post('/api/captures', json={'text':'Synthetic'}).status_code == 403
    assert agent.post(f'/api/captures/{identifier}/finish', json={'retain_source':False}).status_code == 403
    assert human.post(f'/api/captures/{identifier}/finish', json={'retain_source':True}).json()['status'] == 'retained_until_expiry'
    assert human.post('/api/agent/access', json={'enabled':False}).json()['enabled'] is False
    assert agent.get(f'/api/captures/{identifier}').status_code == 403
    assert human.post(f'/api/captures/{identifier}/finish', json={'retain_source':False}).status_code == 200
    assert human.get(f'/api/captures/{identifier}').status_code == 404


def test_library_http_uses_shared_support_and_persists_capture_relaunch(tmp_path):
    from uuid import uuid4
    app, human, agent = clients(tmp_path)
    change = agent.post('/api/changes', json=dict(base_revision=0, idempotency_key='fact', summary='Synthetic fact', operations=[dict(op='upsert', title='Synthetic support', body='Local', kind='fact')])).json()
    accepted = human.post(f"/api/changes/{change['id']}/approve").json()
    item = accepted['operations'][0]['id']
    page, book, section = [str(uuid4()) for _ in range(3)]
    command = dict(base_revision=1, idempotency_key='reader', summary='Synthetic reader', operations=[
        dict(op='upsert_page', id=page, base_revision=0, title='Synthetic page', state='published', sections=[dict(id=section, kind='factual', body='Readable local knowledge', supports=[dict(item_id=item, revision=1)])]),
        dict(op='upsert_book', id=book, base_revision=0, title='Synthetic book', state='published', page_ids=[page])])
    proposed = agent.post('/api/library/changes', json=command)
    assert proposed.status_code == 200, proposed.text
    proposal = proposed.json()
    assert agent.post(f"/api/library/changes/{proposal['id']}/approve").status_code == 403
    assert agent.post(f"/api/library/changes/{proposal['id']}/reject").status_code == 403
    assert human.post(f"/api/library/changes/{proposal['id']}/approve").status_code == 200
    assert human.get(f'/api/library/books/{book}').json()['page_ids'] == [page]
    assert human.get(f'/api/library/pages/{page}').json()['support_state'] == 'current'
    assert 'project_id' not in human.get('/api/library/changes').text
    capture = human.post('/api/captures', json={'text':'Synthetic survives relaunch','intent':'request'}).json()
    old_session = human.cookies.get('kh_session')
    app2, human2, agent2 = clients(tmp_path)
    state = human2.get('/api/workspace').json()
    assert (state['revision'], state['item_count'], state['book_count']) == (2,1,1)
    assert human2.get(f"/api/captures/{capture['id']}").json()['text'] == 'Synthetic survives relaunch'
    assert human2.get('/api/library/books').json()['books'][0]['id'] == book
    assert TestClient(app2, cookies={'kh_session':old_session}).get('/api/workspace').status_code == 401
    assert agent2.get(f"/api/captures/{capture['id']}").status_code == 403


def test_legacy_http_cannot_create_or_select_knowledge_partitions(tmp_path):
    app, human, agent = clients(tmp_path)
    response = human.post('/api/projects', json={'name':'Forbidden partition'})
    assert response.status_code == 410
    assert response.headers['Deprecation'] == 'true'
    assert human.get('/api/projects/arbitrary/knowledge').status_code == 410
    assert human.get('/api/workspace').json()['item_count'] == 0
    assert TestClient(app).get('/api/projects').status_code == 401
    assert human.get('/api/projects', headers={'Host':'evil.example'}).status_code == 400
