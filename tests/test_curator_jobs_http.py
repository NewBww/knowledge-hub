from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from knowledge_hub.core import DomainError
from knowledge_hub.store import Store
from test_curator_jobs import Sources


def client_for(tmp_path):
    from knowledge_hub.curator_jobs import CuratorJobs
    from knowledge_hub.curator_jobs_http import register
    app = FastAPI()
    @app.middleware('http')
    async def auth(request: Request, call_next):
        request.state.human = request.headers.get('x-synthetic-human') == 'yes'
        return await call_next(request)
    @app.exception_handler(DomainError)
    async def error(request, exc):
        return JSONResponse({'error': exc.code}, status_code=exc.status)
    jobs = CuratorJobs(Store(tmp_path), sources=Sources())
    register(app, jobs.store, jobs=jobs)
    return TestClient(app), jobs


def test_job_http_requires_human_and_reconnects_to_committed_id(tmp_path):
    client, jobs = client_for(tmp_path)
    headers = {'x-synthetic-human': 'yes'}
    payload = dict(source_ids=['s1'], instruction='Analyze', request_id='request-1')
    assert client.post('/api/curator-jobs', json=payload).status_code == 403
    response = client.post('/api/curator-jobs', json=payload, headers=headers)
    assert response.status_code == 200
    identifier = response.json()['id']
    assert client.post('/api/curator-jobs', json=payload, headers=headers).json()['id'] == identifier
    assert client.get('/api/curator-jobs').status_code == 403
    assert client.get('/api/curator-jobs/' + identifier).status_code == 403
    assert client.get('/api/curator-jobs/' + identifier, headers=headers).json()['status'] == 'queued'
    assert client.post('/api/curator-jobs/' + identifier + '/cancel', json={}).status_code == 403
    assert client.post('/api/curator-jobs/' + identifier + '/cancel', json={}, headers=headers).json()['status'] == 'cancelled'
    assert jobs.get(identifier)['status'] == 'cancelled'
    assert client.post('/api/curator-jobs/' + identifier + '/retry', json={}, headers=headers).status_code == 409
    assert client.post('/api/curator-jobs/' + identifier + '/approve', json={}, headers=headers).status_code == 404


def test_http_bounded_reference_only_commands_and_pagination(tmp_path):
    client, jobs = client_for(tmp_path)
    headers = {'x-synthetic-human': 'yes'}
    for i in range(3):
        assert client.post('/api/curator-jobs', json=dict(source_ids=['s1'], instruction='Analyze', request_id=f'r{i}'), headers=headers).status_code == 200
    first = client.get('/api/curator-jobs?status=queued&limit=2', headers=headers).json()
    assert len(first['jobs']) == 2 and first['next_cursor']
    last = client.get('/api/curator-jobs?status=queued&limit=2&cursor=' + first['next_cursor'], headers=headers).json()
    assert len(last['jobs']) == 1 and last['next_cursor'] is None
    assert client.get('/api/curator-jobs?cursor=bad', headers=headers).status_code == 422
    for payload in [dict(source_ids=['/etc/passwd'], instruction='x', request_id='a'),
                    dict(source_ids=['s1'], instruction='x' * 2001, request_id='b'),
                    dict(source_ids=['s1'], instruction='x', request_id='c', text='not accepted'),
                    dict(source_ids=['s1'] * 11, instruction='x', request_id='d')]:
        assert client.post('/api/curator-jobs', json=payload, headers=headers).status_code == 422
    duplicate = '{"source_ids":["s1"],"instruction":"x","instruction":"y","request_id":"z"}'
    assert client.post('/api/curator-jobs', content=duplicate, headers=headers).status_code == 422
