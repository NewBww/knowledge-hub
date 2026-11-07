"""Synthetic local job tests. No owner data or real provider calls."""
import json
import hashlib
import pytest
from knowledge_hub.core import DomainError
from knowledge_hub.store import Store


class Sources:
    """Test-only registered source boundary, not a production source reader."""
    def __init__(self):
        self.generation = 'g1'
        self.text = 'Synthetic sky is blue.'
        self.revoked = False

    def pin(self, source_ids):
        return [dict(source_id=s, generation=self.generation,
                     sha256=hashlib.sha256(self.text.encode()).hexdigest(),
                     locator='synthetic:' + s, origin={}) for s in source_ids]

    def validate(self, ref):
        if self.revoked:
            raise DomainError('source_revoked', 403)
        if ref['generation'] != self.generation:
            raise DomainError('source_changed')

    def read(self, ref, *, max_chars):
        self.validate(ref)
        if len(self.text) > max_chars:
            raise DomainError('context_size_limit', 413)
        return self.text


def test_enqueue_is_durable_idempotent_and_reference_only(tmp_path):
    from knowledge_hub.curator_jobs import CuratorJobs
    store = Store(tmp_path)
    sources = Sources()
    jobs = CuratorJobs(store, sources=sources)
    with pytest.raises(DomainError, match='approval_required'):
        jobs.submit(['s1'], 'Analyze', 'r1')
    first = jobs.submit(['s1'], 'Analyze', 'r1', human=True)
    replay = CuratorJobs(store, sources=sources).submit(['s1'], 'Analyze', 'r1', human=True)
    assert first['id'] == replay['id']
    assert first['status'] == 'queued'
    assert first['execution_mode'] == 'foreground_resumable'
    assert sources.text not in jobs.path.read_bytes().decode('utf-8', errors='ignore')
    with pytest.raises(DomainError, match='idempotency_conflict'):
        jobs.submit(['s1'], 'Different', 'r1', human=True)
    assert jobs.get(first['id'])['source_references'][0]['generation'] == 'g1'
    assert len(jobs.list()['jobs']) == 1
    assert jobs.path.stat().st_mode & 0o777 == 0o600


def test_cursor_is_bound_to_status_filter(tmp_path):
    from knowledge_hub.curator_jobs import CuratorJobs
    jobs = CuratorJobs(Store(tmp_path), sources=Sources())
    for i in range(3): jobs.submit(['s1'], 'Analyze', f'r{i}', human=True)
    cursor = jobs.list(status='queued', limit=1)['next_cursor']
    with pytest.raises(DomainError, match='invalid_cursor'):
        jobs.list(status='failed', cursor=cursor, limit=1)


def test_native_revocation_serializes_with_final_proposal_publication(tmp_path):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from knowledge_hub.context_sources import ContextSources
    from knowledge_hub.curator_jobs import ContextJobSources, CuratorJobs, CuratorJobWorker
    from knowledge_hub.curator_runtime import CuratorRuntime
    root = tmp_path / 'notes.txt'; root.write_text('Synthetic sky is blue.')
    store = Store(tmp_path / 'data'); connections = configured(store)
    native = ContextSources(store.path.parent); selected = native.register_selected([root])[0]
    jobs = CuratorJobs(store, sources=ContextJobSources(native), connections=connections)
    jobs.submit([selected['id']], 'Analyze', 'r1', human=True)
    original = store.propose
    futures = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        def propose(*args):
            future = pool.submit(native.revoke, selected['id'])
            futures.append(future)
            with pytest.raises(TimeoutError): future.result(timeout=0.1)
            return original(*args)
        store.propose = propose
        runtime = CuratorRuntime(store, connections, execute=lambda *a: draft())
        assert CuratorJobWorker(jobs, runtime=runtime).run_once()['status'] == 'review_ready'
        assert futures[0].result(timeout=3)['status'] == 'revoked'


class Vault:
    def get(self, name):
        return 'SYNTHETIC_TEST_ONLY'


def configured(store):
    from knowledge_hub.connections import Connections
    from knowledge_hub.shared import SharedWarehouse
    SharedWarehouse(store)
    connections = Connections(store, vault=Vault())
    connections._save(dict(connection='openrouter', model='synthetic/model', consent=True,
                           enabled=True, status='checked', generation='synthetic-g1'))
    return connections


def draft():
    return dict(summary='Synthetic proposal', operations=[dict(title='Sky', body='Sky is blue.',
                kind='fact', quote='Synthetic sky is blue.')])


def test_worker_uses_existing_runtime_and_only_creates_pending_review(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('network forbidden'))
    from knowledge_hub.curator_jobs import CuratorJobs, CuratorJobWorker
    from knowledge_hub.curator_runtime import CuratorRuntime
    from knowledge_hub.shared import SharedWarehouse
    store = Store(tmp_path)
    connections = configured(store)
    calls = []
    def execute(model, key, packet, cancel):
        calls.append(packet)
        return draft()
    runtime = CuratorRuntime(store, connections, execute=execute)
    jobs = CuratorJobs(store, sources=Sources(), connections=connections)
    job = jobs.submit(['s1'], 'Analyze', 'r1', human=True)
    result = CuratorJobWorker(jobs, runtime=runtime).run_once()
    assert result['status'] == 'review_ready'
    assert len(calls) == 1 and calls[0]['text'] == 'Synthetic sky is blue.'
    assert calls[0]['intent'] == 'Analyze'
    scope = SharedWarehouse(store).scope()
    changes = store.changes(scope)
    assert len(changes) == 1 and changes[0]['status'] == 'pending'
    assert changes[0]['operations'][0]['evidence'][0]['locator'] == 'synthetic:s1'
    assert store.knowledge(scope)['items'] == []
    assert jobs.get(job['id'])['result']['change_id'] == changes[0]['id']
    assert CuratorJobWorker(jobs, runtime=runtime).run_once() is None


def test_unconfigured_jobs_block_without_inference(tmp_path):
    from knowledge_hub.curator_jobs import CuratorJobs, CuratorJobWorker
    jobs = CuratorJobs(Store(tmp_path), sources=Sources())
    job = jobs.submit(['s1'], 'Analyze', 'r1', human=True)
    assert CuratorJobWorker(jobs).run_once()['status'] == 'blocked'
    assert jobs.get(job['id'])['error'] == 'requires_connection'


def crash_worker(root, phase):
    """Real spawned test process; all network operations denied."""
    import os
    import socket
    from pathlib import Path
    from knowledge_hub.curator_jobs import CuratorJobs, CuratorJobWorker
    from knowledge_hub.curator_runtime import CuratorRuntime
    from knowledge_hub.connections import Connections
    def no_network(*args, **kwargs):
        raise AssertionError('network forbidden in crash fixture')
    socket.socket = no_network
    store = Store(Path(root))
    connections = Connections(store, vault=Vault())
    def execute(model, key, packet, cancel):
        with (Path(root) / 'synthetic-call-count').open('a') as f:
            f.write('call\n')
        return draft()
    runtime = CuratorRuntime(store, connections, execute=execute)
    jobs = CuratorJobs(store, sources=Sources(), connections=connections, clock=lambda: 100.0)
    def hook(stage):
        if stage == phase:
            os._exit(73)
    CuratorJobWorker(jobs, runtime=runtime, stage_hook=hook).run_once()


@pytest.mark.parametrize('phase', ['claimed', 'prepared', 'proposed'])
def test_real_process_death_replays_checkpoint_without_duplicate_proposals(tmp_path, phase):
    import multiprocessing
    from knowledge_hub.curator_jobs import CuratorJobs, CuratorJobWorker
    from knowledge_hub.curator_runtime import CuratorRuntime
    from knowledge_hub.shared import SharedWarehouse
    store = Store(tmp_path)
    connections = configured(store)
    jobs = CuratorJobs(store, sources=Sources(), connections=connections, clock=lambda: 100.0)
    job = jobs.submit(['s1'], 'Analyze', 'r1', human=True)
    process = multiprocessing.get_context('spawn').Process(target=crash_worker, args=(str(tmp_path), phase))
    process.start(); process.join(15)
    if process.is_alive():
        process.kill(); process.join()
        pytest.fail('crash fixture did not stop')
    assert process.exitcode == 73
    restarted = CuratorJobs(store, sources=Sources(), connections=connections, clock=lambda: 300.0)
    calls = []
    runtime = CuratorRuntime(store, connections, execute=lambda *args: calls.append(1) or draft())
    assert CuratorJobWorker(restarted, runtime=runtime).run_once()['status'] == 'review_ready'
    assert calls == ([1] if phase == 'claimed' else [])
    assert len(store.changes(SharedWarehouse(store).scope())) == 1
    assert store.knowledge(SharedWarehouse(store).scope())['items'] == []
    assert restarted.get(job['id'])['attempt_count'] == 2


@pytest.mark.parametrize('action,expected', [('cancel','cancelled'), ('revoke','blocked'),
                                            ('generation','blocked'), ('source_change','stale'), ('quit','paused')])
def test_mid_inference_revocation_and_quit_fence_late_results(tmp_path, action, expected):
    import threading
    from knowledge_hub.curator_jobs import CuratorJobs, CuratorJobWorker
    from knowledge_hub.curator_runtime import CuratorRuntime
    from knowledge_hub.shared import SharedWarehouse
    store = Store(tmp_path); connections = configured(store); sources = Sources()
    jobs = CuratorJobs(store, sources=sources, connections=connections)
    job = jobs.submit(['s1'], 'Analyze', 'r1', human=True)
    stop = threading.Event()
    def execute(*args):
        if action == 'cancel': jobs.cancel(job['id'], human=True)
        elif action == 'revoke': sources.revoked = True
        elif action == 'source_change': sources.generation = 'g2'
        elif action == 'quit': stop.set()
        else:
            state = connections.state(); state['generation'] = 'synthetic-g2'; connections._save(state)
        return draft()
    runtime = CuratorRuntime(store, connections, execute=execute)
    result = CuratorJobWorker(jobs, runtime=runtime, stop=stop).run_once()
    assert result['status'] == expected
    assert store.changes(SharedWarehouse(store).scope()) == []
    if action == 'quit':
        stop.clear()
        runtime = CuratorRuntime(store, connections, execute=lambda *a: draft())
        assert CuratorJobWorker(jobs, runtime=runtime).run_once()['status'] == 'review_ready'


def test_transient_retries_are_scheduled_persisted_and_exhausted(tmp_path):
    from knowledge_hub.curator_jobs import CuratorJobs, CuratorJobWorker
    from knowledge_hub.curator_runtime import CuratorRuntime
    store = Store(tmp_path); connections = configured(store); now = [100.0]
    jobs = CuratorJobs(store, sources=Sources(), connections=connections, clock=lambda: now[0])
    job = jobs.submit(['s1'], 'Analyze', 'r1', human=True)
    def fail(*args): raise DomainError('provider_unavailable', 502)
    runtime = CuratorRuntime(store, connections, execute=fail)
    for attempt in range(1, 4):
        worker = CuratorJobWorker(jobs, runtime=runtime)
        result = worker.run_once()
        assert result['attempt_count'] == attempt
        assert result['status'] == ('retry_wait' if attempt < 3 else 'failed')
        assert worker.run_once() is None
        now[0] += 65
        jobs = CuratorJobs(store, sources=Sources(), connections=connections, clock=lambda: now[0])
    assert jobs.get(job['id'])['attempt_count'] == 3


def test_native_selected_directory_is_pinned_bounded_and_revocation_checked(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    from knowledge_hub.curator_jobs import ContextJobSources, CuratorJobs, CuratorJobWorker
    from knowledge_hub.curator_runtime import CuratorRuntime
    root = tmp_path / 'selected'; root.mkdir()
    (root / 'notes.txt').write_text('Synthetic sky is blue.')
    (root / '.env').write_text('TEST_ONLY_SECRET=must-not-read')
    (root / 'nested').mkdir(); (root / 'nested' / 'other.txt').write_text('Other evidence')
    store = Store(tmp_path / 'appdata'); connections = configured(store)
    native = ContextSources(store.path.parent)
    selected = native.register_selected([root])[0]
    sources = ContextJobSources(native)
    refs = sources.pin([selected['id']])
    assert refs[0]['origin']['files'] == ['nested/other.txt', 'notes.txt']
    assert str(root) not in json.dumps(refs)
    jobs = CuratorJobs(store, sources=sources, connections=connections)
    job = jobs.submit([selected['id']], 'Analyze', 'r1', human=True)
    packets = []
    runtime = CuratorRuntime(store, connections, execute=lambda m, k, p, c: packets.append(p) or draft())
    assert CuratorJobWorker(jobs, runtime=runtime).run_once()['status'] == 'review_ready'
    assert 'must-not-read' not in packets[0]['text']
    native.revoke(selected['id'])
    with pytest.raises(DomainError, match='source_revoked'):
        sources.validate(refs[0])


def test_native_content_changes_do_not_silently_replace_frozen_evidence(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    from knowledge_hub.curator_jobs import ContextJobSources, CuratorJobs, CuratorJobWorker
    root = tmp_path / 'notes.txt'; root.write_text('Synthetic sky is blue.')
    store = Store(tmp_path / 'appdata'); connections = configured(store)
    native = ContextSources(store.path.parent); selected = native.register_selected([root])[0]
    sources = ContextJobSources(native)
    jobs = CuratorJobs(store, sources=sources, connections=connections)
    job = jobs.submit([selected['id']], 'Analyze', 'r1', human=True)
    root.write_text('Changed content')
    assert CuratorJobWorker(jobs).run_once()['status'] == 'stale'
    assert jobs.get(job['id'])['error'] == 'source_changed'


def test_native_quotes_cannot_span_unrelated_files(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    from knowledge_hub.curator_jobs import ContextJobSources, CuratorJobs, CuratorJobWorker
    from knowledge_hub.curator_runtime import CuratorRuntime
    root = tmp_path / 'selected'; root.mkdir()
    (root / 'a.txt').write_text('Synthetic sky')
    (root / 'b.txt').write_text('is blue.')
    store = Store(tmp_path / 'data'); connections = configured(store)
    native = ContextSources(store.path.parent); selected = native.register_selected([root])[0]
    jobs = CuratorJobs(store, sources=ContextJobSources(native), connections=connections)
    jobs.submit([selected['id']], 'Analyze', 'r1', human=True)
    response = draft(); response['operations'][0]['quote'] = 'Synthetic sky\nis blue.'
    runtime = CuratorRuntime(store, connections, execute=lambda *a: response)
    assert CuratorJobWorker(jobs, runtime=runtime).run_once()['error'] == 'invalid_provider_response'


def test_native_manifest_pins_individual_file_digests(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    from knowledge_hub.curator_jobs import ContextJobSources
    root = tmp_path / 'selected'; root.mkdir()
    (root / 'a.txt').write_text('a'); (root / 'b.txt').write_text('b\nc')
    native = ContextSources(tmp_path / 'data'); selected = native.register_selected([root])[0]
    sources = ContextJobSources(native); ref = sources.pin([selected['id']])[0]
    (root / 'a.txt').write_text('a\nb'); (root / 'b.txt').write_text('c')
    with pytest.raises(DomainError, match='source_changed'):
        sources.validate(ref)


def test_native_oversized_or_truncated_navigation_fails_closed(tmp_path):
    from knowledge_hub.context_sources import ContextSources
    from knowledge_hub.curator_jobs import ContextJobSources
    root = tmp_path / 'notes.txt'; root.write_text('x' * 12001)
    native = ContextSources(tmp_path / 'data'); selected = native.register_selected([root])[0]
    with pytest.raises(DomainError, match='context_size_limit'):
        ContextJobSources(native).pin([selected['id']])


def test_expired_lease_is_fenced_and_cancellation_survives_restart(tmp_path):
    from knowledge_hub.curator_jobs import CuratorJobs
    now = [100.0]
    store = Store(tmp_path)
    jobs = CuratorJobs(store, sources=Sources(), clock=lambda: now[0])
    job = jobs.submit(['s1'], 'Analyze', 'r1', human=True)
    lease = jobs.claim('worker1', ttl=5)
    assert lease['id'] == job['id'] and lease['epoch'] == 1
    assert jobs.claim('worker2', ttl=5) is None
    now[0] += 6
    replacement = jobs.claim('worker2', ttl=5)
    assert replacement['epoch'] == 2
    with pytest.raises(DomainError, match='lease_lost'):
        jobs.heartbeat(lease, ttl=5)
    with pytest.raises(DomainError, match='approval_required'):
        jobs.cancel(job['id'])
    jobs.cancel(job['id'], human=True)
    with pytest.raises(DomainError, match='lease_lost'):
        jobs.heartbeat(replacement)
    reopened = CuratorJobs(store, sources=Sources(), clock=lambda: now[0])
    assert reopened.get(job['id'])['status'] == 'cancelled'
    assert reopened.claim('worker3') is None


def test_interrupted_claims_have_a_persisted_retry_budget(tmp_path):
    from knowledge_hub.curator_jobs import CuratorJobs
    now = [100.0]
    jobs = CuratorJobs(Store(tmp_path), sources=Sources(), clock=lambda: now[0])
    job = jobs.submit(['s1'], 'Analyze', 'r1', human=True)
    for i in range(3):
        assert jobs.claim(str(i), ttl=5)['attempt_count'] == i + 1
        now[0] += 6
    assert jobs.claim('exhausted') is None
    assert jobs.get(job['id'])['status'] == 'failed'
    assert jobs.get(job['id'])['error'] == 'retry_budget_exhausted'
    with pytest.raises(DomainError, match='retry_budget_exhausted'):
        jobs.retry(job['id'], human=True)
