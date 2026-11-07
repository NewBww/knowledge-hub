import copy
from uuid import uuid4
import pytest
from knowledge_hub.core import DomainError
from test_library import setup, command, service, propose


def test_review_is_idempotent_and_rejection_never_publishes(tmp_path):
    store, p, item = setup(tmp_path)
    lib = service(store)
    cmd = command(item)
    pending = propose(lib, p, cmd)
    assert propose(lib, p, cmd) == pending
    different = copy.deepcopy(cmd)
    different['summary'] = 'Changed'
    with pytest.raises(DomainError, match='idempotency_conflict'): propose(lib, p, different)
    assert lib.reject(p, pending['id'])['status'] == 'rejected'
    assert lib.reject(p, pending['id'])['status'] == 'rejected'
    with pytest.raises(DomainError, match='not_pending'): lib.approve(p, pending['id'])
    assert lib.books(p) == []
    cmd['idempotency_key'] = str(uuid4())
    approved = lib.approve(p, propose(lib, p, cmd)['id'])
    assert lib.approve(p, approved['id']) == approved
    with pytest.raises(DomainError, match='not_pending'): lib.reject(p, approved['id'])
    assert store.projects()[0]['revision'] == 2


@pytest.mark.parametrize('mutation,error', [('project','stale_revision'), ('page','stale_revision'), ('support','stale_support'), ('support_state','unsupported_publication')])
def test_approval_rechecks_every_recorded_revision_without_partial_write(tmp_path, mutation, error):
    store, p, item = setup(tmp_path)
    lib = service(store)
    cmd = command(item)
    pending = propose(lib, p, cmd)
    with store.connect() as db:
        if mutation == 'project': db.execute('UPDATE projects SET revision=revision+1 WHERE id=?', (p,))
        if mutation == 'support': db.execute('UPDATE items SET revision=revision+1 WHERE id=?', (item,))
        if mutation == 'support_state': db.execute("UPDATE items SET state='needs_review' WHERE id=?", (item,))
        if mutation == 'page':
            import json
            op = cmd['operations'][0]
            payload = dict(op, revision=1, project_id=p)
            db.execute('INSERT INTO library_pages VALUES (?,?,?,?)', (op['id'], p, 1, json.dumps(payload)))
    before = store.projects(), lib.changes(p)
    with pytest.raises(DomainError, match=error): lib.approve(p, pending['id'])
    assert (store.projects(), lib.changes(p)) == before
    assert lib.books(p) == []


@pytest.mark.parametrize('method', ['approve', 'reject'])
def test_unknown_change_is_scoped_domain_error(tmp_path, method):
    store, p, _ = setup(tmp_path)
    with pytest.raises(DomainError, match='change_not_found'): getattr(service(store), method)(p, str(uuid4()))
