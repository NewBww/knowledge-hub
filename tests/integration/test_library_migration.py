import sqlite3
import pytest
from knowledge_hub.store import Store


def test_v1_migration_backed_up_and_future_guard(tmp_path):
    # Build actual old schema independently; never use an owner database.
    path = tmp_path / 'knowledge.sqlite3'
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,purpose TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE items(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),title TEXT NOT NULL,body TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL,revision INTEGER NOT NULL,evidence TEXT NOT NULL,depends_on TEXT NOT NULL);
        CREATE TABLE changes(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),idempotency_key TEXT NOT NULL,request TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(project_id,idempotency_key));
        INSERT INTO projects VALUES ('synthetic','Synthetic','Preserve',0); PRAGMA user_version=1;''')
    store = Store(tmp_path)
    with store.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
    assert store.projects()[0]['purpose'] == 'Preserve'
    with sqlite3.connect(tmp_path / 'knowledge.sqlite3.v1.bak') as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'items_fts%'").fetchone()[0] == 0
    assert Store(tmp_path).projects() == store.projects()
    with store.connect() as db:
        db.execute('PRAGMA user_version=999')
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match='newer_schema'):
        Store(tmp_path)
    assert path.read_bytes() == before


def test_v1_canonical_items_and_pending_proposals_survive_migration(tmp_path):
    from test_library import setup
    from knowledge_hub.core import Proposal
    store, project, _ = setup(tmp_path)
    pending = store.propose(project, Proposal(base_revision=1, idempotency_key='pending', summary='Keep pending', operations=[dict(op='upsert', title='Pending', body='Not accepted', kind='question')]))
    before = store.knowledge(project), store.changes(project), store.projects()
    with store.connect() as db:
        for table in ('library_books', 'library_pages', 'library_changes'):
            db.execute(f'DROP TABLE {table}')
        db.execute('PRAGMA user_version=1')
    reopened = Store(tmp_path)
    assert (reopened.knowledge(project), reopened.changes(project), reopened.projects()) == before
    assert reopened.changes(project)[-1] == pending
    assert reopened.path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / 'knowledge.sqlite3.v1.bak').stat().st_mode & 0o777 == 0o600


def test_migration_failure_rolls_back_new_tables_and_version(tmp_path):
    # A real SQLite DDL failure after the first table must not leave a partial v2.
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute('DROP TABLE library_books')
        db.execute('DROP TABLE library_pages')
        db.execute('DROP TABLE library_changes')
        db.execute('CREATE VIEW library_pages AS SELECT id FROM projects')
        db.execute('PRAGMA user_version=1')
    # CREATE TABLE IF NOT EXISTS ignores the colliding view: migration must validate schema.
    with pytest.raises((RuntimeError, sqlite3.OperationalError)):
        Store(tmp_path)
    with sqlite3.connect(store.path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='library_books'").fetchone()
