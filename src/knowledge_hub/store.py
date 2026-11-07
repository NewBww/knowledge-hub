"""SQLite canonical store. Every call uses a short-lived connection."""
import sqlite3
import json
from .core import Proposal, DomainError
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


class Store:
    def __init__(self, data_dir: Path):
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = data_dir / 'knowledge.sqlite3'
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 3:
                raise RuntimeError('newer_schema: upgrade Knowledge Hub before opening this database')
            if version == 1:
                backup = self.path.with_name(self.path.name + '.v1.bak')
                if not backup.exists():
                    self.backup(backup)
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, purpose TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    title TEXT NOT NULL, body TEXT NOT NULL, kind TEXT NOT NULL,
                    state TEXT NOT NULL, revision INTEGER NOT NULL,
                    evidence TEXT NOT NULL, depends_on TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS changes (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    idempotency_key TEXT NOT NULL, request TEXT NOT NULL,
                    payload TEXT NOT NULL, UNIQUE(project_id,idempotency_key));
            ''')
            try:
                db.executescript('''
                    CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(id UNINDEXED, title, body);
                    CREATE TRIGGER IF NOT EXISTS items_insert AFTER INSERT ON items BEGIN
                        INSERT INTO items_fts(id,title,body) VALUES (new.id,new.title,new.body);
                    END;
                    CREATE TRIGGER IF NOT EXISTS items_update AFTER UPDATE ON items BEGIN
                        DELETE FROM items_fts WHERE id=old.id;
                        INSERT INTO items_fts(id,title,body) VALUES (new.id,new.title,new.body);
                    END;
                ''')
            except sqlite3.OperationalError as exc:
                raise RuntimeError('SQLite FTS5 support is required; install an FTS5-enabled Python runtime') from exc
            self.fts_available = True
        if version < 2:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for table in ('library_books', 'library_pages'):
                    existing = db.execute('SELECT type FROM sqlite_master WHERE name=?', (table,)).fetchone()
                    if existing and existing['type'] != 'table':
                        raise RuntimeError('invalid_library_schema')
                    db.execute(f'''CREATE TABLE IF NOT EXISTS {table} (
                        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                        revision INTEGER NOT NULL, payload TEXT NOT NULL)''')
                db.execute('''CREATE TABLE IF NOT EXISTS library_changes (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                    idempotency_key TEXT NOT NULL, request TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(project_id,idempotency_key))''')
                db.execute('PRAGMA user_version=2')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def projects(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('''SELECT p.*,
                (SELECT count(*) FROM items WHERE project_id=p.id) AS item_count,
                (SELECT count(*) FROM items WHERE project_id=p.id AND state='needs_review') AS review_count
                FROM projects p ORDER BY name,id''')]

    def create_project(self, name: str, purpose: str = ''):
        identifier = str(uuid4())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='shared_workspace'").fetchone():
                raise DomainError('project_scope_removed', 410)
            db.execute('INSERT INTO projects(id,name,purpose) VALUES (?,?,?)', (identifier, name, purpose))
        return next(p for p in self.projects() if p['id'] == identifier)

    def _project(self, db, project_id):
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='shared_workspace'").fetchone():
            canonical = db.execute('SELECT scope FROM shared_workspace').fetchone()
            if canonical is None or canonical['scope'] != project_id:
                raise DomainError('project_scope_removed', 410)
        row = db.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        if row is None:
            raise DomainError('project_not_found', 404)
        return dict(row)

    @staticmethod
    def _item(row):
        item = dict(row)
        for field in ('evidence', 'depends_on'):
            item[field] = json.loads(item[field])
        return item

    def knowledge(self, project_id, q='', state=''):
        with self.connect() as db:
            self._project(db, project_id)
            if '\x00' in q:
                return {'items': [], 'total': 0}
            sql = 'SELECT * FROM items WHERE project_id=?'
            args = [project_id]
            if state:
                sql += ' AND state=?'
                args.append(state)
            if q.strip():
                sql += ' AND id IN (SELECT id FROM items_fts WHERE items_fts MATCH ?)'
                args.append('"' + q.strip().replace('"', '""') + '"')
            items = [self._item(row) for row in db.execute(sql + ' ORDER BY title,id', args)]
        return {'items': items, 'total': len(items)}

    def get_item(self, project_id, item_id):
        with self.connect() as db:
            self._project(db, project_id)
            row = db.execute('SELECT * FROM items WHERE project_id=? AND id=?', (project_id, item_id)).fetchone()
            if row is None:
                raise DomainError('item_not_found', 404)
            return self._item(row)

    def context(self, project_id):
        with self.connect() as db:
            db.execute('BEGIN')
            project = self._project(db, project_id)
            items = [self._item(row) for row in db.execute('SELECT * FROM items WHERE project_id=? ORDER BY title,id', (project_id,))]
        return {'project': project, 'revision': project['revision'],
                **{state: [item for item in items if item['state'] == state]
                   for state in ('current', 'needs_review', 'unresolved', 'superseded')}}

    def backup(self, target: Path):
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.resolve() == self.path.resolve() or target.exists():
            raise ValueError('Backup destination must be a new file')
        with self.connect() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        target.chmod(0o600)
        return target

    def changes(self, project_id):
        with self.connect() as db:
            self._project(db, project_id)
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM changes WHERE project_id=? ORDER BY rowid', (project_id,))]

    def propose(self, project_id, proposal: Proposal):
        operations = proposal.model_dump(mode='json')['operations']
        for operation in operations:
            operation['id'] = operation['id'] or str(uuid4())
        change = dict(id=str(uuid4()), project_id=project_id, base_revision=proposal.base_revision,
                      status='pending', summary=proposal.summary, operations=operations,
                      impact={'affected_ids': sorted(op['id'] for op in operations), 'review_required_ids': []})
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._project(db, project_id)
            existing = db.execute('SELECT request,payload FROM changes WHERE project_id=? AND idempotency_key=?', (project_id, proposal.idempotency_key)).fetchone()
            if existing:
                if existing['request'] != proposal.model_dump_json():
                    raise DomainError('idempotency_conflict')
                return json.loads(existing['payload'])
            if self._project(db, project_id)['revision'] != proposal.base_revision:
                raise DomainError('stale_revision')
            for op in proposal.operations:
                references = [str(identifier) for identifier in op.depends_on]
                if op.id is not None:
                    references.append(str(op.id))
                for identifier in references:
                    if not db.execute('SELECT 1 FROM items WHERE project_id=? AND id=?', (project_id, identifier)).fetchone():
                        raise DomainError('invalid_reference', 422)
            changed = {op['id'] for op in operations}
            affected = set(changed)
            items = [self._item(row) for row in db.execute('SELECT * FROM items WHERE project_id=?', (project_id,))]
            while True:
                expanded = affected | {item['id'] for item in items if affected.intersection(item['depends_on'])}
                if expanded == affected:
                    break
                affected = expanded
            review = affected - changed
            states = {item['id']: item['state'] for item in items}
            unresolved = {op['id'] for op in operations if op['kind'] == 'question'}
            while True:
                invalid = review | {op['id'] for op in operations if any(
                    dependency in review or dependency in unresolved or (dependency not in changed and states[dependency] != 'current')
                    for dependency in op['depends_on'])}
                if invalid == review:
                    break
                review = invalid
            change['impact'] = {'affected_ids': sorted(affected), 'review_required_ids': sorted(review)}
            db.execute('INSERT INTO changes VALUES (?,?,?,?,?)', (change['id'], project_id, proposal.idempotency_key, proposal.model_dump_json(), json.dumps(change)))
        return change

    def _change(self, db, project_id, change_id):
        self._project(db, project_id)
        row = db.execute('SELECT payload FROM changes WHERE project_id=? AND id=?', (project_id, change_id)).fetchone()
        if row is None:
            raise DomainError('change_not_found', 404)
        return json.loads(row[0])

    def _save_change(self, db, change):
        db.execute('UPDATE changes SET payload=? WHERE id=?', (json.dumps(change), change['id']))

    def reject(self, project_id, change_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            change = self._change(db, project_id, change_id)
            if change['status'] == 'approved':
                raise DomainError('not_pending')
            change['status'] = 'rejected'
            self._save_change(db, change)
        return change

    def approve(self, project_id, change_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            change = self._change(db, project_id, change_id)
            if change['status'] == 'approved':
                return change
            if change['status'] != 'pending':
                raise DomainError('not_pending')
            project = self._project(db, project_id)
            if project['revision'] != change['base_revision']:
                raise DomainError('stale_revision')
            revision = project['revision'] + 1
            for operation in change['operations']:
                db.execute('''INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body,
                    kind=excluded.kind,state=excluded.state,revision=excluded.revision,
                    evidence=excluded.evidence,depends_on=excluded.depends_on''',
                    (operation['id'], project_id, operation['title'], operation['body'], operation['kind'],
                     'unresolved' if operation['kind'] == 'question' else 'current', revision, json.dumps(operation['evidence']), json.dumps(operation['depends_on'])))
            for identifier in change['impact']['review_required_ids']:
                db.execute("UPDATE items SET state='needs_review',revision=? WHERE project_id=? AND id=?", (revision, project_id, identifier))
            db.execute('UPDATE projects SET revision=? WHERE id=?', (revision, project_id))
            change.update(status='approved', result_revision=revision)
            self._save_change(db, change)
        return change

