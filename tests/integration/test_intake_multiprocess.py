"""Real spawned processes, held service boundaries, no race-by-sleep loops."""
import multiprocessing as mp
from pathlib import Path

from knowledge_hub.curator import Curator
from knowledge_hub.intake import Intake
from knowledge_hub.intake_models import CaptureInput
from knowledge_hub.store import Store


def _claim_worker(root, project, capture, connection, hold):
    from knowledge_hub.core import DomainError
    curator = Curator(Store(Path(root)))
    if hold:
        original = curator.intake.save
        def save(payload):
            connection.send('before_save')
            assert connection.recv() == 'release'
            original(payload)
        curator.intake.save = save
    connection.send('ready')
    assert connection.recv() == 'claim'
    connection.send('attempt')
    try:
        result = curator.claim(project, capture['id'], 'worker', capture['snapshot_sha256'], 0)
    except DomainError as error:
        result = error.code
    connection.send(result)


def _start(target, *args):
    context = mp.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=target, args=(*args, child))
    process.start()
    child.close()
    return process, parent


def _recv(connection):
    assert connection.poll(15), 'worker blocked or died'
    return connection.recv()


def _finish(*processes):
    for process in processes:
        process.join(15)
        if process.is_alive():
            process.kill()
            process.join()
            raise AssertionError('deadlock')
        assert process.exitcode == 0


def _claim_entry(root, project, capture, hold, connection):
    _claim_worker(root, project, capture, connection, hold)


def test_two_process_claim_has_one_winner(tmp_path):
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    capture = Intake(store).create(project, CaptureInput(text='one work item'))
    Curator(store).set_agent_access(project, True)
    # Initialize both services before the first holds the compound operation.
    first, a = _start(_claim_entry, str(tmp_path), project, capture, True)
    second, b = _start(_claim_entry, str(tmp_path), project, capture, False)
    try:
        assert _recv(a) == _recv(b) == 'ready'
        a.send('claim')
        assert _recv(a) == 'attempt'
        assert _recv(a) == 'before_save'
        b.send('claim')
        assert _recv(b) == 'attempt'
        # Old code lets b finish while a holds a stale, unpersisted lease.
        # A bounded wait permits the corrected lock to block b instead.
        early = b.recv() if b.poll(1) else None
        a.send('release')
        results = [_recv(a), early if early is not None else _recv(b)]
        assert sum(isinstance(result, dict) for result in results) == 1, results
        assert results.count('capture_claimed') == 1
        winner = next(result for result in results if isinstance(result, dict))
        assert Intake(Store(tmp_path)).get(project, capture['id'])['claim']['claim_token'] == winner['claim_token']
    finally:
        if first.is_alive():
            a.send('release')
        _finish(first, second)


def _submission(capture, lease):
    return {'snapshot_sha256': capture['snapshot_sha256'], 'claim_token': lease['claim_token'],
            'base_revision': 0, 'summary': 'Synthetic draft',
            'operations': [{'op': 'upsert', 'title': 'Fact', 'body': 'Text', 'kind': 'fact'}],
            'library_suggestions': [{'book_title': 'Guide', 'page_title': 'Topic', 'body': 'Original'}]}


def _commit_then_wait(root, project, capture_id, submission, connection):
    store = Store(Path(root))
    curator = Curator(store)
    original = store.propose
    def propose(*args):
        result = original(*args)
        connection.send(result)
        connection.recv()  # Parent kills us after the real SQLite commit.
        return result
    store.propose = propose
    curator.curation_submit(project, capture_id, submission)


def test_killed_submit_recovers_exact_result_without_changed_suggestions(tmp_path):
    import copy
    from datetime import datetime, timedelta, timezone
    import pytest
    from knowledge_hub.core import DomainError
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    curator = Curator(store)
    capture = curator.intake.create(project, CaptureInput(text='source'))
    curator.set_agent_access(project, True)
    lease = curator.claim(project, capture['id'], 'agent', capture['snapshot_sha256'], 0)
    submission = _submission(capture, lease)
    process, connection = _start(_commit_then_wait, str(tmp_path), project, capture['id'], submission)
    try:
        committed = _recv(connection)
    finally:
        process.kill()
        process.join(15)
    restarted = Curator(Store(tmp_path))
    changed = copy.deepcopy(submission)
    changed['library_suggestions'][0]['body'] = 'Not the accepted submission'
    with pytest.raises(DomainError, match='idempotency_conflict'):
        restarted.curation_submit(project, capture['id'], changed)
    saved = restarted.intake.get(project, capture['id'])
    saved['claim']['expires_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    restarted.intake.save(saved)
    # Canonical revision may move after the proposal committed; recovery is not a new proposal.
    store.approve(project, committed['id'])
    result = restarted.curation_submit(project, capture['id'], submission)
    assert result['warehouse_change']['id'] == committed['id']
    assert result['library_suggestions'] == submission['library_suggestions']
    assert len(store.changes(project)) == 1
    assert Curator(Store(tmp_path)).curation_submit(project, capture['id'], submission) == result


def _operation_worker(root, project, capture, submission, operation, checkpoint, connection):
    from knowledge_hub.core import DomainError
    curator = Curator(Store(Path(root)))
    if checkpoint:
        if operation == 'inspect':
            original = curator.intake.purge
            def purge():
                original()
                connection.send('held')
                assert connection.recv() == 'release'
            curator.intake.purge = purge
        elif operation == 'enable':
            original = curator.access.get
            def get(*args):
                connection.send('held')
                assert connection.recv() == 'release'
                return original(*args)
            curator.access.get = get
        else:
            original = curator.store.propose
            def propose(*args):
                connection.send('held')
                assert connection.recv() == 'release'
                return original(*args)
            curator.store.propose = propose
    connection.send('ready')
    assert connection.recv() == 'run'
    connection.send('attempt')
    try:
        if operation == 'submit':
            result = curator.curation_submit(project, capture['id'], submission)
        elif operation == 'revoke':
            result = curator.set_agent_access(project, False)
        elif operation == 'delete':
            result = curator.intake.delete(project, capture['id'])
        elif operation == 'inspect':
            result = curator.intake.get(project, capture['id'])
        elif operation == 'enable':
            result = curator.set_agent_access(project, True)
        else:
            result = curator.capture_get(project, capture['id'])
    except DomainError as error:
        result = error.code
    connection.send(result)


# Supplemental characterization: these exercise the shared lock already driven
# RED -> GREEN by the two-process claim regression above.
import pytest


@pytest.mark.parametrize('other', ['revoke', 'delete'])
def test_submit_serializes_with_revoke_or_delete(tmp_path, other):
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    curator = Curator(store)
    capture = curator.intake.create(project, CaptureInput(text='source'))
    curator.set_agent_access(project, True)
    lease = curator.claim(project, capture['id'], 'agent', capture['snapshot_sha256'], 0)
    submission = _submission(capture, lease)
    first, a = _start(_operation_worker, str(tmp_path), project, capture, submission, 'submit', True)
    second, b = _start(_operation_worker, str(tmp_path), project, capture, submission, other, False)
    try:
        assert _recv(a) == _recv(b) == 'ready'
        a.send('run')
        assert _recv(a) == 'attempt'
        assert _recv(a) == 'held'
        b.send('run')
        assert _recv(b) == 'attempt'
        assert not b.poll(0.3), 'mutation crossed the held submission transaction'
        a.send('release')
        assert _recv(a)['warehouse_change']['status'] == 'pending'
        assert isinstance(_recv(b), dict)
    finally:
        if first.is_alive():
            a.send('release')
        _finish(first, second)
    assert len(store.changes(project)) == 1
    third, c = _start(_operation_worker, str(tmp_path), project, capture, submission, 'submit', False)
    assert _recv(c) == 'ready'
    c.send('run')
    assert _recv(c) == 'attempt'
    assert _recv(c) == ('agent_access_disabled' if other == 'revoke' else 'capture_not_found')
    _finish(third)


def _operation_worker_close_then_wait(closed, exit_allowed, *args):
    connection = args[-1]
    _operation_worker(*args)
    connection.close()
    closed.set()
    assert exit_allowed.wait(15), 'parent did not finish cleanup'


@pytest.mark.parametrize(('operation', 'other'), [('inspect', 'delete'), ('enable', 'revoke')])
@pytest.mark.parametrize('fail_readback', [False, True])
def test_compound_cleanup_after_worker_closes_pipe(tmp_path, monkeypatch, operation, other, fail_readback):
    # Hold the real first process alive after its pipe closes: is_alive() alone
    # cannot tell cleanup whether another release can safely be sent.
    context = mp.get_context('spawn')
    closed, exit_allowed = context.Event(), context.Event()
    start, recv, finish = _start, _recv, _finish
    workers = []
    first_connection = None
    finished = False

    def start_worker(target, *args):
        nonlocal first_connection
        if not workers:
            process, connection = start(_operation_worker_close_then_wait, closed, exit_allowed, *args)
            first_connection = connection
        else:
            process, connection = start(target, *args)
        workers.append(process)
        return process, connection

    def recv_worker(connection):
        result = recv(connection)
        if connection is first_connection and isinstance(result, dict):
            assert closed.wait(15), 'worker did not close its pipe'
            assert workers[0].is_alive()
            if fail_readback:
                return {'text': 'wrong readback', 'agent_access': False}
        return result

    def finish_workers(*processes):
        nonlocal finished
        exit_allowed.set()
        finish(*processes)
        finished = True

    monkeypatch.setitem(globals(), '_start', start_worker)
    monkeypatch.setitem(globals(), '_recv', recv_worker)
    monkeypatch.setitem(globals(), '_finish', finish_workers)
    try:
        if fail_readback:
            with pytest.raises(AssertionError) as failure:
                test_compound_human_operations_keep_lock_through_readback(tmp_path, operation, other)
            assert failure.traceback[-1].name == 'test_compound_human_operations_keep_lock_through_readback'
            assert "assert result['text']" in str(failure.traceback[-1].statement)
        else:
            test_compound_human_operations_keep_lock_through_readback(tmp_path, operation, other)
        assert finished, 'cleanup skipped process joins and exit-code assertions'
    finally:
        exit_allowed.set()
        for process in workers:
            process.join(15)
            if process.is_alive():
                process.kill()
                process.join()


@pytest.mark.parametrize(('operation', 'other'), [('inspect', 'delete'), ('enable', 'revoke')])
def test_compound_human_operations_keep_lock_through_readback(tmp_path, operation, other):
    store = Store(tmp_path)
    project = store.create_project('Synthetic')['id']
    capture = Intake(store).create(project, CaptureInput(text='source'))
    first, a = _start(_operation_worker, str(tmp_path), project, capture, None, operation, True)
    second, b = _start(_operation_worker, str(tmp_path), project, capture, None, other, False)
    release_attempted = False
    try:
        assert _recv(a) == _recv(b) == 'ready'
        a.send('run')
        assert _recv(a) == 'attempt'
        assert _recv(a) == 'held'
        b.send('run')
        assert _recv(b) == 'attempt'
        early = b.recv() if b.poll(0.5) else None
        release_attempted = True
        a.send('release')
        result = _recv(a)
        assert early is None, 'compound operation released its lock before readback'
        assert result['text'] == 'source' if operation == 'inspect' else result['agent_access'] is True
        assert isinstance(_recv(b), dict)
    finally:
        # A child can close its pipe while is_alive() still returns True.
        # Never retry the normal-path release, including when readback fails.
        if not release_attempted and first.is_alive():
            a.send('release')
        _finish(first, second)

