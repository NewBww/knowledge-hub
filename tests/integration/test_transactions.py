"""Supplemental transaction/failure tests exercise the real SQLite boundary."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from knowledge_hub.store import Store
from knowledge_hub.core import Proposal, DomainError


def proposal(key):
    return Proposal(base_revision=0, idempotency_key=key, summary='Synthetic', operations=[
        {'op':'upsert', 'title':'First', 'body':'Synthetic only', 'kind':'fact'},
        {'op':'upsert', 'title':'Second', 'body':'Synthetic only', 'kind':'fact'}])


def test_failure_after_first_item_rolls_back_items_fts_revision_status(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    pending = store.propose(p, proposal('atomic'))
    with store.connect() as db:
        db.execute("""CREATE TRIGGER synthetic_failure BEFORE INSERT ON items
            WHEN new.title='Second' BEGIN SELECT RAISE(ABORT, 'synthetic_failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='synthetic_failure'):
        store.approve(p, pending['id'])
    assert store.knowledge(p) == {'items':[], 'total':0}
    assert store.knowledge(p, q='First')['total'] == 0
    assert store.projects()[0]['revision'] == 0
    assert store.changes(p) == [pending]
    with store.connect() as db:
        db.execute('DROP TRIGGER synthetic_failure')
    assert store.approve(p, pending['id'])['result_revision'] == 1
    assert store.knowledge(p)['total'] == 2


def test_competing_approvals_accept_one_revision_only(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    first = store.propose(p, proposal('first'))
    second = store.propose(p, proposal('second'))
    barrier = Barrier(2)
    def apply(change):
        barrier.wait(timeout=5)
        try:
            return store.approve(p, change['id'])['status']
        except DomainError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(apply, [first, second])) == ['approved','stale_revision']
    assert store.projects()[0]['revision'] == 1
    assert store.knowledge(p)['total'] == 2


def test_concurrent_idempotency_returns_same_proposal(tmp_path):
    store = Store(tmp_path)
    p = store.create_project('Synthetic', '')['id']
    barrier = Barrier(2)
    def propose(_):
        barrier.wait(timeout=5)
        return store.propose(p, proposal('duplicate'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(propose, [0,1]))
    assert results[0] == results[1]
    assert store.changes(p) == [results[0]]


def test_future_schema_is_refused_without_modification(tmp_path):
    path = tmp_path / 'knowledge.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version=999')
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match='newer_schema'):
        Store(tmp_path)
    assert path.read_bytes() == before

