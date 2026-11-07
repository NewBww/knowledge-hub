from fastapi.testclient import TestClient

from knowledge_hub.http import create_app


def test_production_factory_mounts_human_jobs(tmp_path):
    app = create_app(tmp_path, human_token='test-human', agent_token='test-agent')
    with TestClient(app) as client:
        response = client.get('/api/curator-jobs', headers={'Authorization': 'Bearer test-agent'})
        assert response.status_code == 403
        response = client.post('/api/session', headers={'Authorization': 'Bearer test-human'})
        assert response.status_code == 200
        response = client.get('/api/curator-jobs')
        assert response.status_code == 200
        assert app.state.curator_jobs is not None


def test_production_worker_starts_and_joins_with_app_lifetime(tmp_path):
    app = create_app(tmp_path, human_token='test-human', agent_token='test-agent')
    with TestClient(app):
        thread = app.state.curator_job_thread
        assert thread.is_alive()
        assert not app.state.curator_job_stop.is_set()
    assert app.state.curator_job_stop.is_set()
    assert not thread.is_alive()


def test_production_worker_processes_selected_source_into_pending_review(tmp_path, monkeypatch):
    import time
    from test_curator_jobs import configured, draft
    from knowledge_hub.curator_runtime import CuratorRuntime
    from knowledge_hub.shared import SharedWarehouse

    app = create_app(tmp_path / 'data', human_token='test-human', agent_token='test-agent')
    app.state.curator_jobs.connections = configured(app.state.store)
    source = tmp_path / 'synthetic.txt'
    source.write_text('Synthetic sky is blue.')
    selected = app.state.context_sources.register_selected([source])[0]
    calls = []

    def synthetic_provider(runtime, configuration, packet):
        calls.append(packet)
        return draft()

    monkeypatch.setattr(CuratorRuntime, '_call', synthetic_provider)
    with TestClient(app) as client:
        assert client.post('/api/session', headers={'Authorization': 'Bearer test-human'}).status_code == 200
        response = client.post('/api/curator-jobs', json={
            'source_ids': [selected['id']], 'instruction': 'Understand this synthetic source',
            'request_id': 'production-lifecycle-test'})
        assert response.status_code == 200, response.text
        job_id = response.json()['id']
        deadline = time.monotonic() + 3
        job = client.get('/api/curator-jobs/' + job_id).json()
        while time.monotonic() < deadline:
            job = client.get('/api/curator-jobs/' + job_id).json()
            if job['status'] != 'queued' and job['status'] != 'running':
                break
            time.sleep(0.02)
        assert job['status'] == 'review_ready', job
        assert len(calls) == 1
        scope = SharedWarehouse(app.state.store).scope()
        assert app.state.store.knowledge(scope)['items'] == []
