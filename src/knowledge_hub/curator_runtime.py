"""App-owned one-item Curator worker; never approves, schedules or starts on init."""
import json
import multiprocessing
import os
import tempfile
import threading
import time
from pathlib import Path
from .connections import require_human
from .connection_transport import validate_draft
from .core import DomainError
from .curator import Curator, CurationSubmission
from .intake import Intake, data_lock
from .intake_models import CaptureInput
from .store import Store


# Fixed public diagnostics only: never serialize arbitrary exception text/status.
_WORKER_ERRORS = {
    'unsupported_capability': 409, 'missing_cli': 409,
    'unsupported_cli_version': 409, 'unsupported_model': 422,
    'conflicting_cli_policy': 409, 'unsafe_local_storage': 409,
    'invalid_configuration': 422, 'invalid_provider_response': 502,
    'context_size_limit': 413, 'provider_response_size_limit': 502,
    'cli_auth_or_execution_failed': 502, 'provider_http_error': 502,
    'provider_unavailable': 502, 'curator_timeout': 504, 'curator_cancelled': 409,
}


def _provider_child(pipe):
    from .connection_transport import OpenRouterAdapter, MAX_RESPONSE
    try:
        payload = json.loads(pipe.recv_bytes(200000))
        connection = payload.get('connection', 'openrouter')
        if connection == 'openrouter':
            draft = OpenRouterAdapter().complete(payload['model'], payload['key'], payload['packet'])
        elif connection == 'hermes':
            from .cli_models import HermesProxyAdapter
            draft = HermesProxyAdapter(Path(payload['root'])).complete(payload['model'], payload['packet'])
        elif connection == 'gemini':
            from .cli_models import GeminiAdapter
            draft = GeminiAdapter(Path(payload['root']), executable=payload['executable'],
                                  node_executable=payload['node_executable']).complete(
                                      payload['model'], payload['packet'], threading.Event(), timeout=25)
        else:
            raise DomainError('unsupported_capability')
        response = json.dumps(draft).encode()
        if len(response) > MAX_RESPONSE:
            raise DomainError('provider_response_size_limit', 502)
        pipe.send_bytes(response)
    except DomainError as error:
        code = error.code if error.code in _WORKER_ERRORS else 'curator_execution_failed'
        pipe.send_bytes(json.dumps({'error': code}).encode())
    except Exception:
        # Never pass request/credential/transport exceptions across the process boundary.
        pipe.send_bytes(b'{"error":"curator_execution_failed"}')


def _isolated_entry(pipe, directory, target):
    os.environ.clear()
    os.environ.update(HOME=directory, TMPDIR=directory, PATH='/usr/bin:/bin', LANG='en_US.UTF-8')
    os.chdir(directory)
    os.umask(0o077)
    try:
        target(pipe)
    finally:
        pipe.close()


def bounded_inference(root, model, key, packet, cancel, *, timeout=40, target=None,
                      connection='openrouter', executable=None, node_executable=None):
    """Killable app-owned text-only worker with fixed adapter dispatch.

    Frozen entry points must call multiprocessing.freeze_support() before GUI
    startup. Source subprocess execution is tested; packaged dispatch is a
    separate acceptance gate. No hard address-space memory cap is claimed.
    """
    from .connection_transport import MAX_RESPONSE
    if cancel.is_set():
        raise DomainError('curator_cancelled')
    with tempfile.TemporaryDirectory(prefix='curator-task-', dir=root) as directory:
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe()
        process = context.Process(target=_isolated_entry, args=(child, directory, target or _provider_child), daemon=True)
        deadline = time.monotonic() + timeout
        try:
            process.start()
            child.close()
            parent.send_bytes(json.dumps({'connection': connection, 'root': str(Path(root).resolve()),
                                         'model': model, 'key': key, 'packet': packet,
                                         'executable': executable, 'node_executable': node_executable}).encode())
            while not parent.poll(0.03):
                if cancel.is_set():
                    raise DomainError('curator_cancelled')
                if time.monotonic() >= deadline:
                    raise DomainError('curator_timeout', 504)
                if not process.is_alive():
                    raise DomainError('curator_execution_failed', 502)
            if cancel.is_set():
                raise DomainError('curator_cancelled')
            result = json.loads(parent.recv_bytes(MAX_RESPONSE))
            if not isinstance(result, dict):
                raise DomainError('curator_execution_failed', 502)
            if result.get('error'):
                code = result['error'] if result['error'] in _WORKER_ERRORS else 'curator_execution_failed'
                raise DomainError(code, _WORKER_ERRORS.get(code, 502))
            return result
        except DomainError:
            raise
        except Exception:
            raise DomainError('curator_execution_failed', 502) from None
        finally:
            parent.close()
            child.close()
            if process.pid:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1)
                process.close()


class CuratorRuntime:
    def __init__(self, store, connections, *, scope=None, execute=None):
        self.store = store
        self.connections = connections
        self.scope = scope or self._shared_scope
        self.execute = execute
        self.cancelled = threading.Event()
        self._running = threading.Lock()

    def _shared_scope(self):
        from .shared import SharedWarehouse
        return SharedWarehouse(self.store).scope()

    def cancel(self):
        self.cancelled.set()

    def _call(self, state, packet):
        if self.cancelled.is_set():
            raise DomainError('curator_cancelled')
        connection = state['connection']
        if connection not in {'openrouter', 'copilot', 'opencode', 'hermes', 'gemini'}:
            raise DomainError('unsupported_capability')
        if state['consent'] is not True:
            raise DomainError('privacy_consent_required', 403)
        root = self.store.path.parent
        try:
            if connection in {'copilot', 'opencode'}:
                from .cli_connections import CLIAdapter
                executable = self.connections.discover(connection)
                if not executable or not Path(executable).is_absolute():
                    raise DomainError('missing_cli', 409)
                response = CLIAdapter(connection, root, executable=executable, cancel=self.cancelled).complete(
                    state['model'], None, packet, consented=True)
            elif connection == 'openrouter':
                key = self.connections._vault().get(self.connections.credential_name())
                if not key:
                    raise DomainError('sign_in_required', 403)
                response = (self.execute(state['model'], key, packet, self.cancelled) if self.execute is not None
                            else bounded_inference(root, state['model'], key, packet, self.cancelled))
            else:
                executable = node = None
                if connection == 'gemini':
                    # Resolve fixed official clients before the worker clears PATH.
                    executable = self.connections.discover('gemini')
                    node = self.connections.discover('node')
                    if not executable or not Path(executable).is_absolute() or not node or not Path(node).is_absolute():
                        raise DomainError('missing_cli', 409)
                response = bounded_inference(root, state['model'], None, packet, self.cancelled,
                                             connection=connection, executable=executable, node_executable=node)
            if self.cancelled.is_set():
                raise DomainError('curator_cancelled')
            return validate_draft(json.dumps(response), packet['text'])
        except DomainError:
            raise
        except Exception:
            raise DomainError('curator_execution_failed', 502) from None

    def _submit(self, curator, scope, capture, lease, draft):
        locator = 'capture:' + capture['id'] + '#' + capture['snapshot_sha256']
        operations = [{**{k: op[k] for k in ('title', 'body', 'kind')}, 'op': 'upsert',
                       'evidence': [{'kind': 'document', 'locator': locator, 'label': op['quote']}]} for op in draft['operations']]
        payload = CurationSubmission.model_validate({
            'snapshot_sha256': capture['snapshot_sha256'], 'claim_token': lease['claim_token'],
            'base_revision': lease['base_revision'], 'summary': draft['summary'], 'operations': operations})
        return curator.curation_submit(scope, capture['id'], payload)

    def check(self, *, human=False):
        require_human(human)
        if not self._running.acquire(blocking=False):
            raise DomainError('curator_busy')
        state = None
        try:
            self.cancelled.clear()  # A new human-requested synthetic check may run while processing is disabled.
            state = self.connections.state()
            packet = {'text': 'Synthetic sky is blue', 'intent': 'Add synthetic knowledge; proposal only.'}
            draft = self._call(state, packet)
            # Run the same domain path against a disposable store, never owner knowledge.
            with tempfile.TemporaryDirectory(prefix='curator-check-', dir=self.store.path.parent) as directory:
                probe = Store(Path(directory))
                scope = probe.create_project('Synthetic connection check')['id']
                curator = Curator(probe)
                curator.set_agent_access(scope, True)
                capture = Intake(probe).create(scope, CaptureInput(text=packet['text']))
                lease = curator.claim(scope, capture['id'], 'synthetic-app-check', capture['snapshot_sha256'], 0)
                result = self._submit(curator, scope, capture, lease, draft)
                saved = Intake(probe).get(scope, capture['id'])
                pending = probe.changes(scope)
                if (saved['result'] != result or len(pending) != 1 or pending[0]['status'] != 'pending'
                        or probe.knowledge(scope)['items']):
                    raise DomainError('diagnostic_readback_failed')
            with data_lock(self.store.path.parent):
                if self.cancelled.is_set():
                    raise DomainError('curator_cancelled')
                current = self.connections._load()
                if any(current.get(k) != state.get(k) for k in ('connection', 'model', 'consent', 'generation')):
                    raise DomainError('configuration_changed')
                current.update(status='checked', enabled=False, last_error=None)
                self.connections._save(current)
            return {'status': 'checked', 'synthetic': True, 'proposal_status': 'pending', 'accepted_count': 0}
        except DomainError as error:
            with data_lock(self.store.path.parent):
                current = self.connections._load()
                if state is not None and all(current.get(k) == state.get(k) for k in ('connection', 'model', 'consent', 'generation')):
                    current.update(status='check_failed', enabled=False, last_error=error.code)
                    self.connections._save(current)
            raise
        finally:
            self._running.release()

    def _release_claim(self, curator, scope, capture_id, token):
        with data_lock(self.store.path.parent):
            saved = curator.intake.get(scope, capture_id)
            # A committed submission is recovered by the existing domain command;
            # do not drop its binding or another worker's replacement claim.
            if not saved.get('submission_sha256') and saved.get('claim', {}).get('claim_token') == token:
                saved.pop('claim', None)
                curator.intake.save(saved)

    def run_once(self, *, human=False):
        require_human(human)
        if self.cancelled.is_set():
            raise DomainError('curator_cancelled')
        if not self._running.acquire(blocking=False):
            raise DomainError('curator_busy')
        lease = capture = curator = scope = state = None
        try:
            state = self.connections.state()
            if not state['enabled'] or state['status'] != 'checked':
                raise DomainError('curator_disabled', 403)
            scope = self.scope()
            curator = Curator(self.store)
            queue = curator.capture_list(scope, limit=100)['captures']
            for item in queue:
                if item['status'] != 'pending_agent':
                    continue
                try:
                    lease = curator.claim(scope, item['id'], 'app-managed-curator', item['snapshot_sha256'], curator._revision(scope), ttl_seconds=120)
                    capture = item
                    break
                except DomainError as error:
                    if error.code not in {'capture_claimed', 'capture_already_proposed'}:
                        raise
            if not capture:
                return {'status': 'idle'}
            packet = curator.capture_get(scope, capture['id'], max_chars=12000)
            if packet['intent'] == 'Request something':
                self._release_claim(curator, scope, capture['id'], lease['claim_token'])
                return {'status': 'human_pending', 'capture_id': capture['id'], 'reason': 'request_requires_external_agent',
                        'suggestion': {'kind': 'request', 'body': packet['text']}}
            if packet['next_offset'] is not None:
                raise DomainError('source_requires_external_agent', 409)
            texts = [packet['text']]
            for file in packet['files']:
                if file['status'] != 'extracted':
                    raise DomainError('source_requires_external_agent', 409)
                remaining = 12000 - sum(len(text) + 1 for text in texts)
                if remaining < 1:
                    raise DomainError('source_requires_external_agent', 409)
                source = curator.capture_get(scope, capture['id'], source_id=file['id'], max_chars=remaining)
                if source['next_offset'] is not None:
                    raise DomainError('source_requires_external_agent', 409)
                texts.append(source['text'])
            draft = self._call(state, {'text': '\n'.join(texts), 'intent': packet['intent'][:500]})
            # Recheck human revocation/configuration before any proposal write.
            with data_lock(self.store.path.parent):
                if self.cancelled.is_set():
                    raise DomainError('curator_cancelled')
                current = self.connections._load()
                if not current['enabled'] or any(current.get(k) != state.get(k) for k in ('connection', 'model', 'consent', 'generation')):
                    raise DomainError('configuration_changed')
                result = self._submit(curator, scope, capture, lease, draft)
            return {'status': 'ready_for_review', 'capture_id': capture['id'], 'result': result}
        except DomainError as error:
            if lease and capture:
                self._release_claim(curator, scope, capture['id'], lease['claim_token'])
            with data_lock(self.store.path.parent):
                current = self.connections._load()
                if state is not None and all(current.get(k) == state.get(k) for k in ('connection', 'model', 'consent', 'generation')):
                    current['last_error'] = error.code
                    self.connections._save(current)
            raise
        finally:
            self._running.release()
