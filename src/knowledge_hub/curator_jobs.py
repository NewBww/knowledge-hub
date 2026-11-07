"""Local durable proposal jobs. Construction never starts a worker or inference.

The host owns foreground worker lifetime: stop on Quit, resume on reopen. No
LaunchAgent, hidden service, automatic approval or provider fallback is installed.
Source services implement pin(ids), validate(reference), read(reference,
max_chars=...). Only registered references, never paths, are accepted.
"""
import base64
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from pydantic import ConfigDict, Field
from .connections import require_human
from .core import DomainError, StrictModel
from .intake import data_lock


class SubmitJob(StrictModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source_ids: list[str] = Field(min_length=1, max_length=10)
    instruction: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9._:-]+$')


class SourceReference(StrictModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source_id: str = Field(min_length=1, max_length=200)
    generation: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    locator: str = Field(min_length=1, max_length=1000)
    origin: dict = Field(default_factory=dict)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


class CuratorJobs:
    def __init__(self, store, *, sources, connections=None, clock=None):
        self.store, self.sources, self.connections = store, sources, connections
        self.clock = clock or time.time
        self.path = store.path.parent / 'curator-jobs.sqlite3'
        if self.path.is_symlink():
            raise DomainError('unsafe_local_storage')
        with data_lock(store.path.parent), self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                request_id TEXT UNIQUE NOT NULL, request TEXT NOT NULL,
                status TEXT NOT NULL, due REAL NOT NULL, payload TEXT NOT NULL)''')
        self.path.chmod(0o600)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _load(self, db, identifier):
        row = db.execute('SELECT payload FROM jobs WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise DomainError('job_not_found', 404)
        return json.loads(row[0])

    def _save(self, db, job):
        job['updated_at'] = self.clock()
        db.execute('UPDATE jobs SET status=?,due=?,payload=? WHERE id=?',
                   (job['status'], job['next_attempt_at'], _json(job), job['id']))

    def _public(self, job):
        return {k: v for k, v in job.items() if k not in {'checkpoint', 'policy', 'worker'}}

    def get(self, identifier):
        with self._db() as db:
            return self._public(self._load(db, identifier))

    def submit(self, source_ids, instruction, request_id, *, human=False):
        require_human(human)
        try:
            command = SubmitJob(source_ids=source_ids, instruction=instruction, request_id=request_id)
            if (len(set(source_ids)) != len(source_ids) or
                    any(not s or len(s) > 200 or '/' in s or '\\' in s or '\x00' in s for s in source_ids)):
                raise ValueError()
        except (ValueError, TypeError):
            raise DomainError('invalid_request', 422) from None
        request = command.model_dump_json()
        with data_lock(self.store.path.parent), self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT id,request FROM jobs WHERE request_id=?', (request_id,)).fetchone()
            if row:
                if row['request'] != request:
                    raise DomainError('idempotency_conflict')
                return self._public(self._load(db, row['id']))
            refs = [SourceReference.model_validate(r).model_dump() for r in self.sources.pin(source_ids)]
            if [r['source_id'] for r in refs] != source_ids or len(_json(refs).encode()) > 16000:
                raise DomainError('invalid_source_reference', 422)
            for ref in refs:
                self.sources.validate(ref)
            now = self.clock()
            job = dict(id=str(uuid4()), status='queued', stage='queued', instruction=instruction,
                       source_references=refs, created_at=now, updated_at=now, next_attempt_at=now,
                       attempt_count=0, max_attempts=3, epoch=0, lease_until=0, heartbeat_at=None,
                       error=None, result=None, checkpoint=None, policy=self._policy(), worker=None,
                       execution_mode='foreground_resumable', background_continuation='not_configured')
            db.execute('INSERT INTO jobs(id,request_id,request,status,due,payload) VALUES (?,?,?,?,?,?)',
                       (job['id'], request_id, request, job['status'], now, _json(job)))
            return self._public(job)

    def _policy(self):
        if self.connections is None:
            return None
        state = self.connections.state()
        if not state.get('connection') or not state.get('generation'):
            return None
        return {k: state.get(k) for k in ('connection', 'model', 'generation', 'profile_id')}

    def _authorize(self, job):
        if not job['policy'] or self.connections is None:
            raise DomainError('requires_connection')
        state = self.connections.state()
        if not state.get('enabled') or state.get('consent') is not True or state.get('status') != 'checked':
            raise DomainError('curator_disabled', 403)
        if any(state.get(k) != v for k, v in job['policy'].items()):
            raise DomainError('configuration_changed')
        for ref in job['source_references']:
            self.sources.validate(ref)
        return state

    def _fenced(self, db, lease):
        job = self._load(db, lease['id'])
        if (job['status'] != 'running' or job['epoch'] != lease['epoch'] or
                job['worker'] != lease['worker'] or job['lease_until'] <= self.clock()):
            raise DomainError('lease_lost')
        return job

    def claim(self, worker, *, ttl=120):
        if not isinstance(ttl, (int, float)) or not 1 <= ttl <= 300:
            raise DomainError('invalid_lease', 422)
        with data_lock(self.store.path.parent), self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            now = self.clock()
            rows = db.execute("SELECT payload FROM jobs WHERE (status IN ('queued','retry_wait','paused') AND due<=?) OR status='running' ORDER BY seq", (now,)).fetchall()
            for row in rows:
                job = json.loads(row[0])
                if job['status'] == 'running' and job['lease_until'] > now:
                    continue
                if job['attempt_count'] >= job['max_attempts']:
                    job.update(status='failed', error='retry_budget_exhausted', worker=None, lease_until=0)
                    self._save(db, job)
                    continue
                recovered = job['status'] == 'running'
                job.update(status='running', worker=worker, epoch=job['epoch'] + 1,
                           attempt_count=job['attempt_count'] + 1, heartbeat_at=now,
                           lease_until=now + ttl, error='interrupted_attempt' if recovered else None)
                self._save(db, job)
                return job
        return None

    def heartbeat(self, lease, *, ttl=120):
        if not 1 <= ttl <= 300:
            raise DomainError('invalid_lease', 422)
        with data_lock(self.store.path.parent), self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._fenced(db, lease)
            job.update(heartbeat_at=self.clock(), lease_until=self.clock() + ttl)
            self._save(db, job)
            return job

    def cancel(self, identifier, *, human=False):
        require_human(human)
        with data_lock(self.store.path.parent), self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._load(db, identifier)
            if job['status'] != 'review_ready':
                job.update(status='cancelled', checkpoint=None, worker=None, lease_until=0,
                           error=None, epoch=job['epoch'] + 1)
                self._save(db, job)
            return self._public(job)

    def retry(self, identifier, *, human=False):
        require_human(human)
        with data_lock(self.store.path.parent), self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._load(db, identifier)
            if job['attempt_count'] >= job['max_attempts']:
                raise DomainError('retry_budget_exhausted')
            if job['status'] not in {'failed', 'blocked', 'retry_wait', 'paused'}:
                raise DomainError('job_not_retryable')
            for ref in job['source_references']:
                self.sources.validate(ref)
            if job['policy'] is None:
                job['policy'] = self._policy()
            job.update(status='queued', error=None, next_attempt_at=self.clock(), worker=None, lease_until=0)
            self._save(db, job)
            return self._public(job)

    @contextmanager
    def _source_guard(self, refs):
        guard = getattr(self.sources, 'guard', None)
        if guard is None:
            yield
        else:
            with guard(refs):
                yield

    def checkpoint(self, lease, proposal):
        from .core import Proposal
        proposal = Proposal.model_validate(proposal).model_dump(mode='json')
        if len(_json(proposal).encode()) > 65536:
            raise DomainError('provider_response_size_limit', 502)
        with data_lock(self.store.path.parent), self._source_guard(lease['source_references']), self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._fenced(db, lease)
            self._authorize(job)
            job.update(checkpoint=proposal, stage='prepared')
            self._save(db, job)
            return job

    def publish(self, lease, scope, *, after_propose=None):
        """Replay journal bridges our DB and Store.propose's idempotent command.

        Hold fencing and the app root lock across this SHORT local commit, never
        inference. A process death after Store commit replays the saved payload.
        """
        from .core import Proposal
        with data_lock(self.store.path.parent), self._source_guard(lease['source_references']), self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._fenced(db, lease)
            self._authorize(job)
            if not job['checkpoint']:
                raise DomainError('missing_checkpoint')
            proposal = Proposal.model_validate(job['checkpoint'])
            change = self.store.propose(scope, proposal)
            # Exact target readback, not merely a successful write call.
            with self.store.connect() as canonical:
                saved = self.store._change(canonical, scope, change['id'])
            if saved != change:
                raise DomainError('proposal_readback_failed')
            if after_propose:
                after_propose('proposed')
            job.update(status='review_ready', stage='review_ready', checkpoint=None,
                       result={'change_id': change['id'], 'proposal_status': change['status'],
                               'canonical_changes_applied': False}, worker=None, lease_until=0, error=None)
            self._save(db, job)
            return self._public(job)

    def failure(self, lease, code):
        transient = {'provider_unavailable', 'curator_timeout'}
        blocked = {'requires_connection', 'curator_disabled', 'configuration_changed', 'source_revoked',
                   'source_unavailable', 'source_expired', 'agent_access_disabled', 'privacy_consent_required',
                   'sign_in_required', 'missing_cli', 'unsupported_capability'}
        stale = {'stale_revision', 'source_changed', 'stale_source', 'capture_integrity_error'}
        known = transient | blocked | stale | {'invalid_provider_response', 'context_size_limit',
                    'provider_response_size_limit', 'source_digest_mismatch', 'worker_paused'}
        safe = code if code in known else 'curator_execution_failed'
        with data_lock(self.store.path.parent), self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            job = self._fenced(db, lease)
            retrying = safe in transient and job['attempt_count'] < job['max_attempts']
            status = ('retry_wait' if retrying else 'blocked' if safe in blocked else
                      'stale' if safe in stale else 'paused' if safe == 'worker_paused' else 'failed')
            job.update(status=status, error=safe, worker=None, lease_until=0,
                       next_attempt_at=self.clock() + min(60, 2 ** job['attempt_count']) if retrying else self.clock())
            if safe in blocked | stale:
                job['checkpoint'] = None
            self._save(db, job)
            return self._public(job)

    def list(self, *, status='', cursor='', limit=20):
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise DomainError('invalid_request', 422)
        statuses = {'queued', 'running', 'paused', 'retry_wait', 'blocked', 'stale', 'failed', 'cancelled', 'review_ready'}
        if status and status not in statuses:
            raise DomainError('invalid_request', 422)
        try:
            if not isinstance(cursor, str) or len(cursor) > 512:
                raise ValueError()
            token = json.loads(base64.urlsafe_b64decode(cursor.encode() + b'=' * (-len(cursor) % 4))) if cursor else {'after': 0, 'status': status}
            after = token['after']
            if type(after) is not int or after < 0 or token['status'] != status:
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise DomainError('invalid_cursor', 422) from None
        with self._db() as db:
            rows = db.execute('SELECT seq,payload FROM jobs WHERE seq>? AND (?=\'\' OR status=?) ORDER BY seq LIMIT ?',
                              (after, status, status, limit + 1)).fetchall()
        return dict(jobs=[self._public(json.loads(r['payload'])) for r in rows[:limit]],
                    next_cursor=base64.urlsafe_b64encode(_json({'after': rows[limit - 1]['seq'], 'status': status}).encode()).decode().rstrip('=') if len(rows) > limit else None)


class ContextJobSources:
    """Adapter to the native-consented ContextSources service, no path access.

    Directory navigation is deterministic and bounded; truncation blocks rather
    than pretending the whole selection was analyzed. Only a file-name manifest
    and digest persist. Content is re-read under current grant/ignore policy.
    """
    def __init__(self, native):
        self.native = native

    @contextmanager
    def guard(self, references):
        # The grant DB is app-owned. A short reserved transaction serializes
        # native revocation against checkpoint/proposal publication, without
        # holding a grant lock during inference or opening selected paths here.
        db = sqlite3.connect(self.native.database, timeout=5)
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                for ref in references:
                    row = db.execute('SELECT status,generation FROM context_sources WHERE id=?', (ref['source_id'],)).fetchone()
                    if row is None or row[0] != 'active':
                        raise DomainError('source_revoked', 403)
                    if str(row[1]) != ref['generation']:
                        raise DomainError('source_changed')
                yield
        finally:
            db.close()

    def _snapshot(self, source_id):
        try:
            row = self.native._row(source_id)
            if row['kind'] == 'file':
                paths = ['']
            else:
                queue, paths, visited = [''], [], 0
                while queue:
                    relative = queue.pop(0)
                    visited += 1
                    if visited > 50:
                        raise DomainError('context_size_limit', 413)
                    listing = self.native.list(source_id, relative)
                    if listing['truncated']:
                        raise DomainError('context_size_limit', 413)
                    for entry in listing['entries']:
                        if entry['kind'] == 'directory':
                            queue.append(entry['relative_path'])
                        else:
                            paths.append(entry['relative_path'])
                        if len(paths) > 20 or len(queue) > 50:
                            raise DomainError('context_size_limit', 413)
                paths.sort()
            texts = []
            remaining = 12000
            for relative in paths:
                result = self.native.read(source_id, relative)
                if result['truncated'] or len(result['text']) > remaining:
                    raise DomainError('context_size_limit', 413)
                texts.append(result['text'])
                remaining -= len(result['text']) + 1
            if not texts or not any(t.strip() for t in texts):
                raise DomainError('source_unavailable')
            self.native._recheck(row)
            text = '\n'.join(texts)
            digest = hashlib.sha256(text.encode()).hexdigest()
            ref = dict(source_id=source_id, generation=str(row['generation']), sha256=digest,
                       locator='context:' + source_id + '#' + str(row['generation']) + ':' + digest,
                       origin={'files': paths, 'file_sha256': [hashlib.sha256(t.encode()).hexdigest() for t in texts]})
            return ref, text
        except DomainError as exc:
            if exc.code in {'context_source_revoked', 'context_permission_changed'}:
                raise DomainError('source_revoked', 403) from None
            if exc.code in {'context_file_changed', 'context_source_changed'}:
                raise DomainError('source_changed') from None
            if exc.code == 'context_size_limit':
                raise
            raise DomainError('source_unavailable', 409) from None

    def pin(self, source_ids):
        return [self._snapshot(identifier)[0] for identifier in source_ids]

    def validate(self, ref):
        current, _ = self._snapshot(ref['source_id'])
        if any(current[k] != ref[k] for k in ('generation', 'sha256', 'origin', 'locator')):
            raise DomainError('source_changed')

    def evidence(self, ref, quote):
        from urllib.parse import quote as encode_path
        self.validate(ref)
        evidence = []
        for path, digest in zip(ref['origin']['files'], ref['origin']['file_sha256']):
            result = self.native.read(ref['source_id'], path)
            if result['truncated'] or hashlib.sha256(result['text'].encode()).hexdigest() != digest:
                raise DomainError('source_changed')
            if quote in result['text']:
                evidence.append({'kind': 'document',
                                 'locator': 'context:' + ref['source_id'] + '/' + encode_path(path, safe='/') + '#' + digest,
                                 'label': quote[:1000]})
        return evidence

    def read(self, ref, *, max_chars):
        current, text = self._snapshot(ref['source_id'])
        if current != ref:
            raise DomainError('source_changed')
        if len(text) > max_chars:
            raise DomainError('context_size_limit', 413)
        return text


class _JobCancellation:
    def __init__(self, jobs, lease, stop):
        self.jobs, self.lease, self.stop = jobs, lease, stop
        self.reason = None
        self.last_heartbeat = jobs.clock()

    def is_set(self):
        if self.reason:
            return True
        if self.stop is not None and self.stop.is_set():
            self.reason = 'worker_paused'
            return True
        try:
            with data_lock(self.jobs.store.path.parent), self.jobs._db() as db:
                current = self.jobs._fenced(db, self.lease)
                self.jobs._authorize(current)
            if self.jobs.clock() - self.last_heartbeat >= 10:
                self.jobs.heartbeat(self.lease)
                self.last_heartbeat = self.jobs.clock()
        except DomainError as exc:
            self.reason = exc.code
            return True
        return False


class CuratorJobWorker:
    """Explicit host-owned runner; runtime calls are the existing bounded adapters.

    runtime/stage_hook are internal test seams, never request fields. Do not share
    the one-item UI runtime instance: its cancellation event has another lifetime.
    """
    def __init__(self, jobs, *, runtime=None, stop=None, stage_hook=None):
        from .curator_runtime import CuratorRuntime
        self.jobs = jobs
        self.runtime = runtime or (CuratorRuntime(jobs.store, jobs.connections) if jobs.connections else None)
        self.stop, self.stage_hook = stop, stage_hook
        self.worker = str(uuid4())

    def _stage(self, stage):
        if self.stage_hook:
            self.stage_hook(stage)

    def run_once(self):
        from .connection_transport import validate_draft
        from .shared import SharedWarehouse
        if self.stop is not None and self.stop.is_set():
            return None
        lease = self.jobs.claim(self.worker)
        if lease is None:
            return None
        cancel = _JobCancellation(self.jobs, lease, self.stop)
        try:
            self._stage('claimed')
            state = self.jobs._authorize(lease)
            scope = SharedWarehouse(self.jobs.store).scope()
            if cancel.is_set():
                raise DomainError(cancel.reason)
            if not lease['checkpoint']:
                texts = []
                remaining = 12000
                for ref in lease['source_references']:
                    if cancel.is_set():
                        raise DomainError(cancel.reason)
                    text = self.jobs.sources.read(ref, max_chars=remaining)
                    if not isinstance(text, str) or len(text) > remaining:
                        raise DomainError('context_size_limit', 413)
                    if hashlib.sha256(text.encode()).hexdigest() != ref['sha256']:
                        raise DomainError('source_digest_mismatch')
                    texts.append(text)
                    remaining -= len(text) + 1
                with self.jobs.store.connect() as db:
                    base = self.jobs.store._project(db, scope)['revision']
                self.runtime.cancelled = cancel
                response = self.runtime._call(state, {'text': '\n'.join(texts), 'intent': lease['instruction']})
                if cancel.is_set():
                    raise DomainError(cancel.reason)
                response = validate_draft(_json(response), '\n'.join(texts))
                operations = []
                for op in response['operations']:
                    # Reject quotes spanning artificial source join boundaries.
                    evidence = []
                    for ref, text in zip(lease['source_references'], texts):
                        if op['quote'] not in text:
                            continue
                        match = getattr(self.jobs.sources, 'evidence', None)
                        evidence.extend(match(ref, op['quote']) if match else
                                        [{'kind': 'document', 'locator': ref['locator'], 'label': op['quote'][:1000]}])
                    if not evidence:
                        raise DomainError('invalid_provider_response', 502)
                    operations.append(dict(op='upsert', title=op['title'], body=op['body'], kind=op['kind'], evidence=evidence))
                lease = self.jobs.checkpoint(lease, dict(base_revision=base, idempotency_key='curator-job:' + lease['id'],
                                                        summary=response['summary'], operations=operations))
                self._stage('prepared')
            if cancel.is_set():
                raise DomainError(cancel.reason)
            return self.jobs.publish(lease, scope, after_propose=self._stage)
        except Exception as exc:
            code = cancel.reason or (exc.code if isinstance(exc, DomainError) else 'curator_execution_failed')
            try:
                return self.jobs.failure(lease, code)
            except DomainError as lost:
                if lost.code != 'lease_lost':
                    raise
                return self.jobs.get(lease['id'])

    def run(self, stop):
        """Host explicitly starts/stops this loop; idle polling has no side effects."""
        self.stop = stop
        while not stop.is_set():
            if self.run_once() is None:
                stop.wait(0.5)
