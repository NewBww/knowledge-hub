"""Deterministic local projections. Budgets measure JSON characters, not tokens."""
import hashlib
import json
from contextlib import contextmanager
from .core import DomainError

DEFAULT_CHARS = 8000
MIN_CHARS = 1024
MAX_CHARS = 32000


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def fits(value, budget):
    # Include the escaped single MCP text representation and conservative framing
    # allowance. HTTP uses the same smaller projection, without duplicated data.
    return len(compact({'content': [{'type': 'text', 'text': compact(value)}], 'isError': False})) + 200 <= budget


class Retrieval:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def _read(self):
        with self.store.connect() as db:
            # SQLite's built-in text length/substr stop at NUL. Plain-text bodies
            # may contain it; offsets here always mean Python/Unicode characters.
            db.create_function('text_length', 1, len, deterministic=True)
            db.create_function('text_segment', 3, lambda text, start, count: text[start-1:start-1+count], deterministic=True)
            db.execute('BEGIN')
            yield db

    @staticmethod
    def _budget(max_chars):
        if not MIN_CHARS <= max_chars <= MAX_CHARS:
            raise DomainError('invalid_budget', 422)

    def search(self, project_id, q='', state='', max_chars=DEFAULT_CHARS, cursor=''):
        self._budget(max_chars)
        with self._read() as db:
            project = self.store._project(db, project_id)
            sql = 'FROM items WHERE project_id=?'
            args = [project_id]
            if state:
                sql += ' AND state=?'
                args.append(state)
            if '\x00' in q:
                sql += ' AND 0'
            elif q.strip():
                sql += ' AND id IN (SELECT id FROM items_fts WHERE items_fts MATCH ?)'
                args.append('"' + q.strip().replace('"', '""') + '"')
            rows = []
            for row in db.execute('''SELECT id,title,kind,state,revision,
                    text_segment(body,max(1,instr(lower(body),lower(?))-40),160) AS snippet,
                    text_length(body) AS body_chars ''' + sql + ' ORDER BY title,id', [q.strip(), *args]):
                item = dict(row)
                item.update(snippet_partial=item.pop('body_chars') > len(item['snippet']), detail_item_id=item['id'])
                rows.append(item)
            return self._page(project, rows, ['search', q, state], max_chars, cursor)

    def get(self, project_id, item_id, max_chars=DEFAULT_CHARS, body_offset=0, expected_revision=None):
        self._budget(max_chars)
        with self._read() as db:
            project = self.store._project(db, project_id)
            if expected_revision is not None and expected_revision != project['revision']:
                raise DomainError('stale_revision', 409)
            row = db.execute('''SELECT id,title,kind,state,revision,text_length(body) AS body_chars,
                json_array_length(evidence) AS evidence_count,text_segment(body,?,?) AS segment
                FROM items WHERE project_id=? AND id=?''', (body_offset + 1, max_chars, project_id, item_id)).fetchone()
            if row is None:
                raise DomainError('item_not_found', 404)
            row = dict(row)
            if not 0 <= body_offset <= row['body_chars']:
                raise DomainError('invalid_body_offset', 422)
            segment = row.pop('segment')
            result = {**row, 'project_id': project_id, 'project_revision': project['revision'],
                      'body': '', 'body_offset': body_offset, 'next_body_offset': body_offset,
                      'body_partial': True, 'budget_unit': 'json_characters', 'max_chars': max_chars,
                      'omissions': ['evidence_details', 'history', 'dependency_details']}
            if not fits(result, max_chars):
                del result['title']
                result['metadata_partial'] = True
            if not fits(result, max_chars):
                raise DomainError('budget_too_small', 422)
            # Binary search the actual escaped JSON envelope, not a body estimate.
            low, high = 0, len(segment)
            while low < high:
                mid = (low + high + 1) // 2
                candidate = {**result, 'body': segment[:mid],
                             'next_body_offset': body_offset + mid if body_offset + mid < row['body_chars'] else None,
                             'body_partial': body_offset > 0 or body_offset + mid < row['body_chars']}
                if fits(candidate, max_chars):
                    low = mid
                else:
                    high = mid - 1
            if not low and body_offset < row['body_chars']:
                raise DomainError('budget_too_small', 422)
            result.update(body=segment[:low],
                          next_body_offset=body_offset + low if body_offset + low < row['body_chars'] else None,
                          body_partial=body_offset > 0 or body_offset + low < row['body_chars'])
            return result

    def context(self, project_id, q='', item_ids=None, max_chars=DEFAULT_CHARS, cursor=''):
        self._budget(max_chars)
        item_ids = sorted(set(item_ids or []))
        if q and item_ids:
            raise DomainError('conflicting_selectors', 422)
        with self._read() as db:
            project = self.store._project(db, project_id)
            rows = {}
            for row in db.execute('''SELECT id,title,kind,state,revision,text_segment(body,1,160) AS snippet,
                    text_length(body) AS body_chars,depends_on,json_array_length(evidence) AS evidence_count
                    FROM items WHERE project_id=? ORDER BY title,id''', (project_id,)):
                item = dict(row)
                item['depends_on'] = json.loads(item['depends_on'])
                rows[item['id']] = item
            if item_ids:
                if any(identifier not in rows for identifier in item_ids):
                    raise DomainError('item_not_found', 404)
                selected = set(item_ids)
            elif q.strip():
                if '\x00' in q:
                    selected = set()
                else:
                    selected = {row[0] for row in db.execute('''SELECT items.id FROM items
                        JOIN items_fts ON items.id=items_fts.id WHERE project_id=? AND items_fts MATCH ?''',
                        (project_id, '"' + q.strip().replace('"', '""') + '"'))}
            else:
                selected = set(list(rows)[:5])
            matched = len(selected)
            orientation = not q and not item_ids
            # Registered prerequisite closure, plus directly connected uncertainty.
            # Fixed point includes prerequisites of warnings; cycles terminate.
            while True:
                expanded = selected | {dep for identifier in selected for dep in rows[identifier]['depends_on'] if dep in rows}
                expanded |= {identifier for identifier, item in rows.items()
                             if item['state'] in ('needs_review', 'unresolved') and selected.intersection(item['depends_on'])}
                if expanded == selected:
                    break
                selected = expanded
            items = []
            for identifier, item in rows.items():
                if identifier in selected:
                    item = {**item, 'snippet_partial': item['body_chars'] > len(item['snippet']),
                            'detail_item_id': identifier}
                    del item['depends_on']
                    items.append(item)
            return self._page(project, items, ['context', q, item_ids], max_chars, cursor, {
                'project': {'id': project['id'], 'name': project['name'][:80], 'name_partial': len(project['name']) > 80,
                            'purpose': project['purpose'][:160], 'purpose_partial': len(project['purpose']) > 160},
                'matched_count': matched, 'orientation_only': orientation,
                'orientation_omitted_count': len(rows) - len(selected) if orientation else 0,
                'coverage': 'registered_dependencies_and_connected_uncertainty_only'})

    def _page(self, project, rows, selector, budget, cursor, extra=None):
        binding = hashlib.sha256(compact([project['id'], project['revision'], selector, 'compact-v1']).encode()).hexdigest()[:24]
        offset = 0
        if cursor:
            try:
                prefix, raw_offset = cursor.split(':')
                offset = int(raw_offset)
                if prefix != binding or not 0 <= offset < len(rows):
                    raise ValueError()
            except (ValueError, TypeError):
                raise DomainError('invalid_cursor', 409) from None
        result = {'project_id': project['id'], 'revision': project['revision'], 'items': [],
                  'total': len(rows), 'included_count': 0, 'has_more': False, 'next_cursor': None,
                  'budget_unit': 'json_characters', 'max_chars': budget,
                  'projection': 'compact-v1', 'omissions': ['full_body', 'evidence_details', 'history']}
        if extra:
            result.update(extra)
        if not fits(result, budget):
            raise DomainError('budget_too_small', 422)
        for index in range(offset, len(rows)):
            row = rows[index]
            candidate = {**result, 'items': result['items'] + [row], 'included_count': len(result['items']) + 1,
                         'has_more': index + 1 < len(rows),
                         'next_cursor': f'{binding}:{index+1}' if index + 1 < len(rows) else None}
            if not fits(candidate, budget):
                if result['items']:
                    break
                # Never split an identifier or present a clipped claim as complete.
                # Advance using an explicit metadata-only stub; inspect body by offset.
                stub = {key: row[key] for key in ('id', 'kind', 'state', 'revision')}
                stub.update(metadata_partial=True, detail_item_id=row['id'])
                candidate['items'] = [stub]
                if not fits(candidate, budget):
                    raise DomainError('budget_too_small', 422)
            result = candidate
        return result
