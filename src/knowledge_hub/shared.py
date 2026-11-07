"""Project-free commands and restart-safe migration to one canonical namespace.

Scoped Store helpers are retained for legacy fixtures, not production destinations.
The SQLite transaction records original rows and a manifest write-ahead journal;
all migration and disclosure changes use the same cross-process lock as intake.
"""
import json
from uuid import uuid4
from .core import DomainError
from .intake import data_lock, fingerprint, private_write


TABLES = ('items', 'changes', 'library_books', 'library_pages', 'library_changes')


def public(value):
    """Remove internal scope selectors recursively without editing canonical data."""
    if isinstance(value, dict):
        return {('warehouse_revision' if key == 'project_revision' else key): public(child)
                for key, child in value.items() if key not in {'project_id', 'project'}}
    if isinstance(value, list):
        return [public(child) for child in value]
    return value


class SharedWarehouse:
    def __init__(self, store):
        self.store = store
        with data_lock(store.path.parent):
            with store.connect() as db:
                existing = db.execute("SELECT 1 FROM sqlite_master WHERE name='shared_workspace'").fetchone()
            if not existing:
                self._migrate()
            self._recover_manifests()

    def _migrate(self):
        store = self.store
        backup = store.path.with_name(store.path.name + '.v2.bak')
        if not backup.exists():
            store.backup(backup)
        # Fail closed before exposing the consolidated namespace, including when
        # the previous process died before its SQLite commit.
        access_path = store.path.parent / 'capture-agent-access.json'
        access_backup = access_path.with_name(access_path.name + '.v2.bak')
        if access_path.is_symlink() or access_backup.is_symlink():
            raise DomainError('unsafe_local_storage')
        if not access_backup.exists():
            private_write(access_backup, access_path.read_bytes() if access_path.exists() else b'{}')
        original_access = access_backup.read_text()
        private_write(access_path, b'{}')
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            projects = [dict(row) for row in db.execute('SELECT * FROM projects ORDER BY id')]
            revisions = {p['id']: p['revision'] for p in projects}
            revision = sum(revisions.values())
            scope = str(uuid4())
            db.execute('CREATE TABLE shared_workspace (scope TEXT PRIMARY KEY, migration TEXT NOT NULL)')
            db.execute('CREATE TABLE shared_legacy_rows (table_name TEXT NOT NULL, id TEXT NOT NULL, original TEXT NOT NULL, PRIMARY KEY(table_name,id))')
            db.execute('CREATE TABLE shared_manifest_journal (id TEXT PRIMARY KEY, original TEXT NOT NULL, target TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE shared_legacy_settings (name TEXT PRIMARY KEY, original TEXT NOT NULL)')
            db.execute('INSERT INTO shared_legacy_settings VALUES (?,?)', ('projects', json.dumps(projects)))
            db.execute('INSERT INTO shared_legacy_settings VALUES (?,?)', ('capture-agent-access.json', original_access))
            db.execute('INSERT INTO projects VALUES (?,?,?,?)', (scope, 'Shared Warehouse', 'Internal canonical namespace', revision))
            for table in TABLES:
                for row in db.execute(f'SELECT * FROM {table}').fetchall():
                    original = dict(row)
                    db.execute('INSERT INTO shared_legacy_rows VALUES (?,?,?)', (table, row['id'], json.dumps(original)))
                    if table == 'items':
                        db.execute('UPDATE items SET project_id=? WHERE id=?', (scope, row['id']))
                        continue
                    payload = json.loads(row['payload'])
                    payload['project_id'] = scope
                    payload['migration'] = {'original_project_id': row['project_id']}
                    if table in ('changes', 'library_changes'):
                        payload['migration']['original_base_revision'] = payload['base_revision']
                        # Only a proposal against its original current tip can
                        # become reviewable against the new union. Stale work
                        # stays stale, with its original request archived intact.
                        if payload['status'] == 'pending':
                            payload['base_revision'] = revision if payload['base_revision'] == revisions[row['project_id']] else -1
                        key = 'legacy:' + row['project_id'] + ':' + row['idempotency_key']
                        db.execute(f'UPDATE {table} SET project_id=?,idempotency_key=?,payload=? WHERE id=?', (scope, key, json.dumps(payload), row['id']))
                    else:
                        db.execute(f'UPDATE {table} SET project_id=?,payload=? WHERE id=?', (scope, json.dumps(payload), row['id']))
            captures = store.path.parent / 'captures'
            if captures.is_symlink():
                raise DomainError('unsafe_local_storage')
            if captures.exists():
                for directory in sorted(captures.iterdir()):
                    if directory.is_symlink():
                        raise DomainError('unsafe_local_storage')
                    manifest = directory / 'capture.json'
                    if manifest.is_symlink():
                        raise DomainError('unsafe_local_storage')
                    if not manifest.is_file():
                        continue
                    original = manifest.read_text()
                    payload = json.loads(original)
                    if payload['id'] != directory.name or payload['project_id'] not in revisions:
                        raise DomainError('capture_integrity_error')
                    snapshot = {k: v for k, v in payload.items() if k not in {'snapshot_sha256', 'status', 'result', 'claim', 'submission_sha256'}}
                    snapshot['status'] = 'pending_agent'
                    if fingerprint(snapshot) != payload['snapshot_sha256']:
                        raise DomainError('capture_integrity_error')
                    payload['migration'] = dict(original_project_id=payload['project_id'], original_snapshot_sha256=payload['snapshot_sha256'])
                    payload['project_id'] = scope
                    # Reconcile a process death between the proposal commit and
                    # manifest completion. Never queue already committed work
                    # under a fresh global idempotency key.
                    committed = db.execute('SELECT payload FROM changes WHERE project_id=? AND idempotency_key=?',
                                           (scope, 'legacy:' + payload['migration']['original_project_id'] + ':capture:' + payload['id'])).fetchone()
                    if committed:
                        if not payload.get('result'):
                            payload['result'] = {'warehouse_change': json.loads(committed[0]), 'library_suggestions': []}
                            payload['migration']['suggestions_require_review'] = True
                        else:
                            payload['result']['warehouse_change'] = json.loads(committed[0])
                        payload['status'] = 'proposed'
                    payload.pop('claim', None)  # Scope-bound processing leases are not global grants.
                    if 'submission_sha256' in payload:
                        payload['migration']['original_submission_sha256'] = payload['submission_sha256']
                        payload.pop('submission_sha256')
                    snapshot = {k: v for k, v in payload.items() if k not in {'snapshot_sha256', 'status', 'result', 'claim', 'submission_sha256'}}
                    snapshot['status'] = 'pending_agent'
                    payload['snapshot_sha256'] = fingerprint(snapshot)
                    db.execute('INSERT INTO shared_manifest_journal(id,original,target) VALUES (?,?,?)', (payload['id'], original, json.dumps(payload)))
            migration = dict(schema=3, status='migrating', legacy_scope_count=len(projects), agent_reconsent_required=bool(projects))
            db.execute('INSERT INTO shared_workspace VALUES (?,?)', (scope, json.dumps(migration)))
            db.execute('PRAGMA user_version=3')

    def _recover_manifests(self):
        with self.store.connect() as db:
            pending = db.execute('SELECT id,target FROM shared_manifest_journal WHERE completed=0 ORDER BY id').fetchall()
        for row in pending:
            path = self.store.path.parent / 'captures' / row['id'] / 'capture.json'
            if path.is_symlink() or path.parent.is_symlink():
                raise DomainError('unsafe_local_storage')
            private_write(path, row['target'].encode())
            with self.store.connect() as db:
                db.execute('UPDATE shared_manifest_journal SET completed=1 WHERE id=?', (row['id'],))
        with self.store.connect() as db:
            migration = json.loads(db.execute('SELECT migration FROM shared_workspace').fetchone()[0])
            if migration['status'] != 'complete':
                migration['status'] = 'complete'
                db.execute('UPDATE shared_workspace SET migration=?', (json.dumps(migration),))

    def scope(self):
        """Internal accessor, never a public destination or permission."""
        with self.store.connect() as db:
            return db.execute('SELECT scope FROM shared_workspace').fetchone()[0]

    def knowledge(self, q='', state=''):
        return public(self.store.knowledge(self.scope(), q, state))

    def get_item(self, item_id):
        return public(self.store.get_item(self.scope(), item_id))

    def changes(self):
        return public(self.store.changes(self.scope()))

    def state(self):
        with self.store.connect() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT scope,migration FROM shared_workspace').fetchone()
            scope = row['scope']
            counts = db.execute("SELECT count(*),sum(state='needs_review') FROM items WHERE project_id=?", (scope,)).fetchone()
            return dict(revision=self.store._project(db, scope)['revision'], item_count=counts[0],
                        review_count=counts[1] or 0,
                        book_count=db.execute('SELECT count(*) FROM library_books WHERE project_id=?', (scope,)).fetchone()[0],
                        migration=json.loads(row['migration']))
