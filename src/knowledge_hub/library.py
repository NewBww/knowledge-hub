"""Local, reviewed reading projections over the canonical Warehouse."""
import json
from uuid import uuid4
from .core import DomainError
from .library_models import LibraryProposal


def rollup(states):
    states = set(states)
    return 'needs_review' if states.intersection({'needs_review', 'superseded'}) else 'unresolved' if 'unresolved' in states else 'current'


class Library:
    def __init__(self, store):
        self.store = store

    def _entities(self, db, project_id, kind):
        return {r['id']: json.loads(r['payload']) for r in db.execute(
            f'SELECT id,payload FROM library_{kind} WHERE project_id=?', (project_id,))}

    def _page(self, db, project_id, page):
        for section in page['sections']:
            for support in section['supports']:
                row = db.execute('SELECT revision,state FROM items WHERE project_id=? AND id=?',
                                 (project_id, support['item_id'])).fetchone()
                support['current_revision'] = row['revision'] if row else None
                support['state'] = ('unresolved' if not row else 'needs_review' if row['revision'] != support['revision'] else row['state'])
            section['support_state'] = ('unresolved' if section['kind'] == 'factual' and not section['supports']
                                        else rollup(s['state'] for s in section['supports']))
        page['support_state'] = rollup(s['support_state'] for s in page['sections'])
        return page

    def _books(self, db, project_id):
        pages = {k: self._page(db, project_id, v) for k, v in self._entities(db, project_id, 'pages').items()}
        books = self._entities(db, project_id, 'books')
        for book in books.values():
            book['pages'] = [pages[i] for i in book['page_ids']]
            book['page_count'] = len(book['pages'])
            book['support_state'] = rollup(p['support_state'] for p in book['pages'])
        return books

    def books(self, project_id):
        with self.store.connect() as db:
            db.execute('BEGIN')
            self.store._project(db, project_id)
            return [{k: v for k, v in b.items() if k != 'pages'} for b in sorted(self._books(db, project_id).values(), key=lambda b: (b['title'], b['id']))]

    def book(self, project_id, book_id):
        with self.store.connect() as db:
            db.execute('BEGIN')
            self.store._project(db, project_id)
            result = self._books(db, project_id).get(book_id)
            if result is None:
                raise DomainError('book_not_found', 404)
            return result

    def page(self, project_id, page_id):
        with self.store.connect() as db:
            db.execute('BEGIN')
            self.store._project(db, project_id)
            page = self._entities(db, project_id, 'pages').get(page_id)
            if page is None:
                raise DomainError('page_not_found', 404)
            return self._page(db, project_id, page)

    def changes(self, project_id):
        with self.store.connect() as db:
            self.store._project(db, project_id)
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM library_changes WHERE project_id=? ORDER BY rowid', (project_id,))]

    def _validate(self, db, project_id, change):
        if self.store._project(db, project_id)['revision'] != change['base_revision']:
            raise DomainError('stale_revision')
        pages = self._entities(db, project_id, 'pages')
        books = self._entities(db, project_id, 'books')
        for op in change['operations']:
            kind = 'pages' if op['op'] == 'upsert_page' else 'books'
            row = db.execute(f'SELECT project_id,revision FROM library_{kind} WHERE id=?', (op['id'],)).fetchone()
            if row and row['project_id'] != project_id:
                raise DomainError('invalid_reference', 422)
            if (row['revision'] if row else 0) != op['base_revision']:
                raise DomainError('stale_revision')
            (pages if kind == 'pages' else books)[op['id']] = op
        for op in change['operations']:
            if op['op'] == 'upsert_book':
                if any(i not in pages for i in op['page_ids']):
                    raise DomainError('invalid_reference', 422)
                if op['state'] == 'published' and any(pages[i]['state'] != 'published' for i in op['page_ids']):
                    raise DomainError('unsupported_publication', 422)
            else:
                if any(i not in pages for i in op['links']):
                    raise DomainError('invalid_reference', 422)
                for section in op['sections']:
                    if op['state'] == 'published' and section['kind'] == 'factual' and not section['supports']:
                        raise DomainError('unsupported_publication', 422)
                    for support in section['supports']:
                        row = db.execute('SELECT revision,state FROM items WHERE project_id=? AND id=?', (project_id, support['item_id'])).fetchone()
                        if row is None:
                            raise DomainError('invalid_reference', 422)
                        if row['revision'] != support['revision']:
                            raise DomainError('stale_support')
                        if op['state'] == 'published' and row['state'] != 'current':
                            raise DomainError('unsupported_publication', 422)
        for book in books.values():
            if book['state'] == 'published' and any(pages[i]['state'] != 'published' for i in book['page_ids']):
                raise DomainError('unsupported_publication', 422)

    def propose(self, project_id, proposal: LibraryProposal):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.store._project(db, project_id)
            existing = db.execute('SELECT request,payload FROM library_changes WHERE project_id=? AND idempotency_key=?', (project_id, proposal.idempotency_key)).fetchone()
            if existing:
                if existing['request'] != proposal.model_dump_json():
                    raise DomainError('idempotency_conflict')
                return json.loads(existing['payload'])
            change = dict(id=str(uuid4()), project_id=project_id, status='pending',
                          **proposal.model_dump(mode='json', exclude={'idempotency_key'}))
            self._validate(db, project_id, change)
            db.execute('INSERT INTO library_changes VALUES (?,?,?,?,?)',
                       (change['id'], project_id, proposal.idempotency_key, proposal.model_dump_json(), json.dumps(change)))
            return change

    def _change(self, db, project_id, change_id):
        self.store._project(db, project_id)
        row = db.execute('SELECT payload FROM library_changes WHERE project_id=? AND id=?', (project_id, change_id)).fetchone()
        if row is None:
            raise DomainError('change_not_found', 404)
        return json.loads(row[0])

    def reject(self, project_id, change_id):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            change = self._change(db, project_id, change_id)
            if change['status'] == 'approved':
                raise DomainError('not_pending')
            change['status'] = 'rejected'
            db.execute('UPDATE library_changes SET payload=? WHERE id=?', (json.dumps(change), change_id))
            return change

    def approve(self, project_id, change_id):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            change = self._change(db, project_id, change_id)
            if change['status'] == 'approved':
                return change
            if change['status'] != 'pending':
                raise DomainError('not_pending')
            self._validate(db, project_id, change)
            for op in change['operations']:
                kind = 'pages' if op['op'] == 'upsert_page' else 'books'
                payload = {k: v for k, v in op.items() if k not in {'op', 'base_revision'}}
                payload.update(project_id=project_id, revision=op['base_revision'] + 1)
                db.execute(f'INSERT INTO library_{kind} VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload', (op['id'], project_id, payload['revision'], json.dumps(payload)))
            revision = change['base_revision'] + 1
            db.execute('UPDATE projects SET revision=? WHERE id=?', (revision, project_id))
            change.update(status='approved', result_revision=revision)
            db.execute('UPDATE library_changes SET payload=? WHERE id=?', (json.dumps(change), change_id))
            return change
