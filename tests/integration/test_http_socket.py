"""A real loopback socket and actual CLI subprocess, no ASGI-only substitute."""
import os
import socket
import subprocess
import sys
import time
import httpx


def test_serve_cli_real_http_cookie_review(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    environment = {**os.environ, 'KNOWLEDGE_HUB_DATA_DIR':str(tmp_path), 'KNOWLEDGE_HUB_HUMAN_TOKEN':'synthetic-human-token'}
    with (tmp_path / 'server.log').open('w+') as log:
        process = subprocess.Popen([sys.executable, '-m', 'knowledge_hub.cli', 'serve', '--port', str(port)],
            env=environment, stdout=log, stderr=log)
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=2) as c:
                for _ in range(100):
                    if process.poll() is not None:
                        break
                    try:
                        if c.get('/api/health').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.05)
                assert process.poll() is None
                assert c.get('/api/health').json()['status'] == 'ok'
                assert c.get('/api/workspace').status_code == 401
                assert c.post('/api/session', headers={'Authorization':'Bearer synthetic-human-token'}).status_code == 200
                assert c.get('/api/workspace').json()['item_count'] == 0
                proposal = {'base_revision':0, 'idempotency_key':'wire', 'summary':'Synthetic', 'operations':[
                    {'op':'upsert', 'title':'Wire apple', 'body':'Synthetic only', 'kind':'fact'}]}
                root = '/api'
                pending = c.post(root+'/changes', json=proposal).json()
                assert c.get(root+'/warehouse').json()['total'] == 0
                assert c.post(root+f"/changes/{pending['id']}/approve").json()['result_revision'] == 1
                assert c.get(root+'/warehouse?q=apple').json()['total'] == 1
                agent = (tmp_path / 'agent.token').read_text()
                with httpx.Client(base_url=f'http://127.0.0.1:{port}') as a:
                    headers = {'Authorization':f'Bearer {agent}'}
                    compact_search = a.get(root+'/agent/search', headers=headers, params={'q':'apple','max_chars':1024})
                    assert compact_search.status_code == 200 and len(compact_search.text) <= 1024
                    assert compact_search.json()['total'] == 1
                    identifier = compact_search.json()['items'][0]['id']
                    assert 'body' not in compact_search.json()['items'][0]
                    context = a.get(root+'/agent/context', headers=headers, params={'item_ids':[identifier]})
                    assert context.status_code == 200 and context.json()['matched_count'] == 1
                    detail = a.get(root+f'/agent/knowledge/{identifier}', headers=headers, params={'max_chars':1024})
                    assert detail.status_code == 200 and len(detail.text) <= 1024
                    assert detail.json()['body'] == 'Synthetic only'
                    assert a.get(root+'/workspace', headers=headers).json()['revision'] == 1
                    assert a.post(root+f"/changes/{pending['id']}/approve", headers={'Authorization':f'Bearer {agent}'}).status_code == 403
        finally:
            process.terminate()
            process.wait(timeout=10)
        log.seek(0)
        assert 'synthetic-human-token' not in log.read()
