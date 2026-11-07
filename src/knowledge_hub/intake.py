"""Transient private local capture storage, separate from canonical Warehouse."""
import hashlib
import json
import os
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
from .core import DomainError
from .intake_models import CaptureInput

# One ordering everywhere: data-root advisory lock, then short Store transactions.
# Keep the lock inode outside captures: purge/delete must never unlink it.
import fcntl
from contextlib import contextmanager

_LOCKS = {}
_REGISTRY_LOCK = threading.Lock()


class _RootLock:
    def __init__(self, root):
        self.path = root / '.capture.lock'
        self.mutex = threading.RLock()
        self.depth = 0
        self.fd = None

    @contextmanager
    def hold(self):
        with self.mutex:
            if not self.depth:
                try:
                    self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                    fcntl.flock(self.fd, fcntl.LOCK_EX)
                except BaseException:
                    if self.fd is not None:
                        os.close(self.fd)
                        self.fd = None
                    raise
            self.depth += 1
            try:
                yield
            finally:
                self.depth -= 1
                if not self.depth:
                    # Closing releases the advisory lock, also on process death.
                    os.close(self.fd)
                    self.fd = None


def _after_fork():
    global _REGISTRY_LOCK
    for lock in _LOCKS.values():
        if lock.fd is not None:
            os.close(lock.fd)
    _LOCKS.clear()
    _REGISTRY_LOCK = threading.Lock()


os.register_at_fork(after_in_child=_after_fork)


def data_lock(root):
    root = Path(root).resolve()
    with _REGISTRY_LOCK:
        lock = _LOCKS.setdefault(root, _RootLock(root))
    return lock.hold()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def private_write(path: Path, data: bytes):
    temporary = path.with_name(str(uuid4()) + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Intake:
    def __init__(self, store):
        self.store = store
        self.root = store.path.parent / 'captures'
        if self.root.is_symlink():
            raise DomainError('unsafe_local_storage', 409)
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.root.chmod(0o700)
        self.purge()

    def _project(self, project_id):
        # Public Store API; no schema coupling.
        self.store.knowledge(project_id)

    def _directory(self, identifier):
        try:
            if str(UUID(identifier)) != identifier:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise DomainError('capture_not_found', 404) from None
        path = self.root / identifier
        if path.is_symlink():
            raise DomainError('unsafe_local_storage')
        return path

    def purge(self):
        with data_lock(self.store.path.parent):
            for directory in self.root.iterdir():
                if directory.is_symlink() or not directory.is_dir():
                    continue
                manifest = directory / 'capture.json'
                if manifest.is_symlink():
                    raise DomainError('unsafe_local_storage')
                if manifest.exists():
                    payload = json.loads(manifest.read_text())
                    if datetime.fromisoformat(payload['expires_at']) <= datetime.now(timezone.utc):
                        shutil.rmtree(directory)

    def create(self, project_id, command: CaptureInput):
        self._project(project_id)
        self.purge()
        identifier = str(uuid4())
        from .request_context import capture_context
        payload = {'id': identifier, 'project_id': project_id, 'text': command.text,
                   'intent': command.intent, 'files': [], 'status': 'pending_agent',
                   **capture_context(self.store, project_id, command.request_context),
                   'expires_at': (datetime.now(timezone.utc) + timedelta(days=command.retention_days)).isoformat()}
        import base64
        import binascii
        from .intake_models import MAX_FILE, MAX_TOTAL
        from .intake_extractors import extract, safe_name
        prepared = []
        total = 0
        for upload in command.files:
            safe_name(upload.name)
            try:
                data = base64.b64decode(upload.content_base64, validate=True)
            except (binascii.Error, ValueError):
                raise DomainError('invalid_base64', 422) from None
            total += len(data)
            if len(data) > MAX_FILE or total > MAX_TOTAL:
                raise DomainError('capture_size_limit', 413)
            file_id = str(uuid4())
            metadata = {'id': file_id, 'name': upload.name, 'media_type': upload.media_type,
                        'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                        **extract(data, upload.media_type)}
            prepared.append((metadata, data))
        payload['files'] = [metadata for metadata, _ in prepared]
        payload['snapshot_sha256'] = fingerprint(payload)
        with data_lock(self.store.path.parent):
            directory = self._directory(identifier)
            directory.mkdir(mode=0o700)
            try:
                for metadata, data in prepared:
                    private_write(directory / metadata['id'], data)
                self.save(payload)
            except Exception:
                shutil.rmtree(directory)
                raise
        return payload

    def save(self, payload):
        with data_lock(self.store.path.parent):
            private_write(self._directory(payload['id']) / 'capture.json', json.dumps(payload).encode())

    def get(self, project_id, identifier):
        with data_lock(self.store.path.parent):
            self._project(project_id)
            self.purge()
            path = self._directory(identifier) / 'capture.json'
            if path.is_symlink():
                raise DomainError('unsafe_local_storage')
            if not path.is_file():
                raise DomainError('capture_not_found', 404)
            payload = json.loads(path.read_text())
            if payload['project_id'] != project_id:
                raise DomainError('capture_not_found', 404)
            snapshot = {key: value for key, value in payload.items() if key not in {'snapshot_sha256', 'status', 'result', 'claim', 'submission_sha256'}}
            snapshot['status'] = 'pending_agent'
            if fingerprint(snapshot) != payload['snapshot_sha256']:
                raise DomainError('capture_integrity_error', 409)
            return payload

    def list(self, project_id):
        self._project(project_id)
        self.purge()
        records = []
        with data_lock(self.store.path.parent):
            for directory in self.root.iterdir():
                if not directory.is_symlink() and directory.is_dir():
                    payload = self.get(project_id, directory.name) if self._belongs(directory, project_id) else None
                    if payload:
                        records.append({key: payload[key] for key in ('id', 'project_id', 'expires_at', 'snapshot_sha256', 'status')})
        return sorted(records, key=lambda row: row['id'])

    def _belongs(self, directory, project_id):
        manifest = directory / 'capture.json'
        return not manifest.is_symlink() and manifest.is_file() and json.loads(manifest.read_text())['project_id'] == project_id

    def delete(self, project_id, identifier):
        with data_lock(self.store.path.parent):
            self.get(project_id, identifier)
            shutil.rmtree(self._directory(identifier))
        return {'status': 'deleted'}
