"""Supplemental end-to-end coverage of the completed projection service."""
from uuid import uuid4
import copy
import json
import os
import socket
import subprocess
import sys
import time
import httpx
import pytest
from knowledge_hub.store import Store
from knowledge_hub.core import DomainError, Proposal
from test_library import setup, command, service, propose


def test_order_crosslinks_refresh_and_reuse_survive_restart(tmp_path):
    store, p, item = setup(tmp_path)
    lib = service(store)
    cmd = command(item)
    first, book = cmd['operations']
    second = copy.deepcopy(first)
    second.update(id=str(uuid4()), title='Second', links=[first['id']])
    second['sections'][0]['id'] = str(uuid4())
    first['links'] = [second['id']]
    book['page_ids'] = [second['id'], first['id']]
    cmd['operations'] = [book, second, first]  # Forward references, not execution order.
    lib.approve(p, propose(lib, p, cmd)['id'])
    lib = service(Store(tmp_path))
    assert [page['id'] for page in lib.book(p, book['id'])['pages']] == book['page_ids']
    assert lib.page(p, second['id'])['links'] == [first['id']]
    update = store.propose(p, Proposal(base_revision=2, idempotency_key='update', summary='Update canonical', operations=[dict(op='upsert', id=item, title='Fact', body='New canonical', kind='fact')]))
    store.approve(p, update['id'])
    assert lib.book(p, book['id'])['support_state'] == 'needs_review'
    for op in (first, second):
        op['base_revision'] = 1
        op['sections'][0]['supports'][0]['revision'] = 3
    refresh = dict(cmd, base_revision=3, idempotency_key='reviewed-refresh', operations=[first, second])
    lib.approve(p, propose(lib, p, refresh)['id'])
    assert lib.book(p, book['id'])['support_state'] == 'current'
    assert store.knowledge(p)['total'] == 1
    assert store.get_item(p, item)['revision'] == 3
    with pytest.raises(DomainError, match='book_not_found'): lib.book(store.create_project('Other')['id'], book['id'])


def test_sqlite_write_failure_rolls_back_whole_publication(tmp_path):
    store, p, item = setup(tmp_path)
    lib = service(store)
    pending = propose(lib, p, command(item))
    with store.connect() as db:
        db.execute("CREATE TRIGGER synthetic_failure BEFORE INSERT ON library_books BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    before = store.projects(), lib.changes(p)
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError): lib.approve(p, pending['id'])
    assert (store.projects(), lib.changes(p)) == before
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM library_pages').fetchone()[0] == 0


def test_real_socket_library_http(tmp_path):
    _, p, item = setup(tmp_path)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    script = """from pathlib import Path
import uvicorn,sys
from knowledge_hub.http import create_app
app=create_app(Path(sys.argv[1]),'synthetic-human','synthetic-agent')
uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[2]),log_level='error')
"""
    with (tmp_path / 'socket.log').open('w') as log:
        process = subprocess.Popen([sys.executable, '-c', script, str(tmp_path), str(port)], stdout=log, stderr=log, env=os.environ.copy())
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=3) as client:
                for _ in range(100):
                    try:
                        if client.get('/api/health').status_code == 200: break
                    except httpx.TransportError: pass
                    time.sleep(.05)
                assert process.poll() is None
                assert client.post('/api/session', headers={'Authorization':'Bearer synthetic-human'}).status_code == 200
                root = '/api/library'
                cmd = command(item)
                change = client.post(root + '/changes', json=cmd).json()
                assert client.post(root + '/changes/' + change['id'] + '/approve').status_code == 200
                assert client.get(root + '/books').json()['books'][0]['page_count'] == 1
                assert client.get(root + '/pages/' + cmd['operations'][0]['id']).json()['sections'][0]['body'] == 'Explanation'
        finally:
            process.terminate()
            process.wait(timeout=10)
