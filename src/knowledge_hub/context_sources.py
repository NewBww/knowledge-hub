"""Read-only, native-consented local evidence. Paths never leave this service."""
from __future__ import annotations

import os
import re
import fnmatch
import time
from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import stat

from .core import DomainError


class ContextSources:
    def __init__(self, data_dir: Path, *, max_read_bytes=131072, max_entries=200,
                 max_search_bytes=1048576, max_results=100):
        self.max_read_bytes = min(131072, max(1, max_read_bytes))
        self.max_entries = min(200, max(1, max_entries))
        self.max_search_bytes = min(1048576, max(1, max_search_bytes))
        self.max_results = min(100, max(1, max_results))
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = data_dir / 'context-sources.sqlite3'
        fd = os.open(self.database, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS context_sources (id TEXT PRIMARY KEY, path TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 1, device INTEGER NOT NULL, inode INTEGER NOT NULL)')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _public(row):
        return {key: row[key] for key in ('id', 'kind', 'name', 'status')}

    def register_selected(self, paths):
        result = []
        with self._connect() as db:
            for selected in paths:
                path = Path(selected).absolute()
                if self._blocked(path.name) or any(self._blocked(part, ancestor=True) for part in path.parts[1:-1]):
                    raise DomainError('context_path_excluded', 403)
                try:
                    fd = self._open_absolute(path)
                    info = os.fstat(fd)
                    os.close(fd)
                except (OSError, ValueError):
                    raise DomainError('context_path_unavailable', 403) from None
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    raise DomainError('context_path_unavailable', 403)
                kind = 'directory' if stat.S_ISDIR(info.st_mode) else 'file'
                source_id = secrets.token_urlsafe(24)
                db.execute('INSERT INTO context_sources VALUES (?,?,?,?,?,?,?,?)',
                           (source_id, str(path), kind, path.name, 'active', 1, info.st_dev, info.st_ino))
                result.append(self._public(db.execute('SELECT * FROM context_sources WHERE id=?', (source_id,)).fetchone()))
        return result

    def sources(self):
        with self._connect() as db:
            return [self._public(row) for row in db.execute('SELECT * FROM context_sources ORDER BY rowid')]

    def _row(self, source_id):
        with self._connect() as db:
            row = db.execute('SELECT * FROM context_sources WHERE id=?', (source_id,)).fetchone()
        if row is None:
            raise DomainError('context_source_not_found', 404)
        if row['status'] != 'active':
            raise DomainError('context_source_revoked', 403)
        return row

    def get(self, source_id):
        with self._connect() as db:
            row = db.execute('SELECT * FROM context_sources WHERE id=?', (source_id,)).fetchone()
        if row is None:
            raise DomainError('context_source_not_found', 404)
        return self._public(row)

    def revoke(self, source_id):
        with self._connect() as db:
            changed = db.execute("UPDATE context_sources SET status='revoked', generation=generation+1 WHERE id=?", (source_id,)).rowcount
            if not changed:
                raise DomainError('context_source_not_found', 404)
        return self.get(source_id)

    @staticmethod
    def _parts(relative_path):
        if not isinstance(relative_path, str) or len(relative_path) > 2048 or '\\' in relative_path or any(ord(c) < 32 for c in relative_path):
            raise DomainError('invalid_context_path', 400)
        if relative_path == '':
            return []
        parts = relative_path.split('/')
        if len(parts) > 32 or any(part in ('', '.', '..') for part in parts):
            raise DomainError('invalid_context_path', 400)
        return parts

    @staticmethod
    def _open_absolute(path):
        # Never resolve first: that would silently authorize a symlink target.
        parts = Path(path).parts
        if not Path(path).is_absolute() or any(p in ('.', '..') for p in parts):
            raise ValueError('invalid path')
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for index, part in enumerate(parts[1:]):
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if index < len(parts) - 2:
                    flags |= os.O_DIRECTORY
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _blocked(name, ancestor=False):
        lower = name.casefold()
        denied = {'node_modules', 'vendor', 'dist', 'build', 'target', '__pycache__',
                  '.git', '.hg', '.svn', '.ssh', '.aws', '.gnupg', '.config', '.venv',
                  'keychains', 'credentials', 'secrets', 'auth', 'authentication'}
        if lower in denied or lower.endswith(('.app', '.bundle', '.framework', '.pkg')):
            return True
        if ancestor:
            return False
        return (lower.startswith('.') or lower.startswith(('id_rsa', 'id_ed25519', 'id_ecdsa'))
                or any(word in lower for word in ('credential', 'secret', 'keychain'))
                or lower in {'authorized_keys', 'known_hosts', 'auth.json', 'token.json', 'tokens.json'}
                or lower.endswith(('.pem', '.key', '.p12', '.pfx', '.keystore', '.db', '.sqlite', '.sqlite3')))

    @staticmethod
    def _glob(pattern, value):
        # Git wildmatch: * never crosses '/', **/ matches zero or more levels.
        # Match components with Python's atomic fnmatch implementation rather
        # than composing backtracking regexes from untrusted ignore patterns.
        from functools import lru_cache
        patterns = pattern.split('/')
        values = value.split('/')

        def component_pattern(raw):
            result = ''
            index = 0
            while index < len(raw):
                char = raw[index]
                if char == '\\' and index + 1 < len(raw):
                    index += 1
                    char = raw[index]
                    result += {'*': '[*]', '?': '[?]', '[': '[[]'}.get(char, char)
                else:
                    result += char
                index += 1
            return result

        @lru_cache(maxsize=4096)
        def match(pattern_index, value_index):
            if pattern_index == len(patterns):
                return value_index == len(values)
            part = patterns[pattern_index]
            if part == '**':
                return (match(pattern_index + 1, value_index)
                        or value_index < len(values) and match(pattern_index, value_index + 1))
            return (value_index < len(values)
                    and fnmatch.fnmatchcase(values[value_index], component_pattern(part))
                    and match(pattern_index + 1, value_index + 1))

        return match(0, 0)

    def _ignore_rules(self, directory_fd, base):
        try:
            fd = os.open('.gitignore', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        except FileNotFoundError:
            return []
        except OSError:
            raise DomainError('context_ignore_policy_unavailable', 403) from None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise DomainError('context_ignore_policy_invalid', 403)
            raw = os.read(fd, 32769)
            if len(raw) > 32768:
                raise DomainError('context_ignore_policy_too_large', 403)
            text = raw.decode('utf-8')
        except UnicodeError:
            raise DomainError('context_ignore_policy_invalid', 403) from None
        finally:
            os.close(fd)
        rules = []
        for line in text.splitlines():
            line = re.sub(r'(?<!\\) +$', '', line)
            if not line or line.startswith('#'):
                continue
            negate = line.startswith('!')
            if negate:
                line = line[1:]
            directory_only = line.endswith('/')
            if directory_only:
                line = line[:-1]
            anchored = line.startswith('/') or '/' in line
            line = line.removeprefix('/')
            if line:
                rules.append((base, line, negate, directory_only, anchored))
        return rules

    def _allowed(self, parts, is_directory, rules):
        if any(self._blocked(part) for part in parts):
            return False
        ignored = False
        for base, pattern, negate, directory_only, anchored in rules:
            if len(parts) <= len(base) or parts[:len(base)] != base:
                continue
            tail = parts[len(base):]
            if directory_only and not is_directory:
                continue
            value = '/'.join(tail) if anchored else tail[-1]
            if self._glob(pattern, value):
                ignored = not negate
        return not ignored

    def _recheck(self, row):
        current = self._row(row['id'])
        if current['generation'] != row['generation']:
            raise DomainError('context_permission_changed', 403)

    def _open(self, row, relative_path):
        parts = self._parts(relative_path)
        if row['kind'] == 'file' and parts:
            raise DomainError('invalid_context_path', 400)
        fd = None
        try:
            fd = self._open_absolute(Path(row['path']))
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != (row['device'], row['inode']):
                raise DomainError('context_source_changed', 403)
            rules = []
            for index, part in enumerate(parts):
                rules.extend(self._ignore_rules(fd, parts[:index]))
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if index < len(parts) - 1:
                    flags |= os.O_DIRECTORY
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
                if not self._allowed(parts[:index + 1], stat.S_ISDIR(os.fstat(fd).st_mode), rules):
                    raise DomainError('context_path_excluded', 403)
            info = os.fstat(fd)
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise DomainError('context_path_unavailable', 403)
            result, fd = fd, None
            return result
        except (OSError, ValueError):
            raise DomainError('context_path_unavailable', 403) from None
        finally:
            if fd is not None:
                os.close(fd)

    @staticmethod
    def _text(raw, truncated):
        if b'\x00' in raw or any(byte < 9 or 13 < byte < 32 for byte in raw):
            raise DomainError('context_binary_unsupported', 415)
        try:
            return raw.decode('utf-8', errors='strict')
        except UnicodeDecodeError as error:
            if truncated and error.reason == 'unexpected end of data' and error.end == len(raw):
                return raw[:error.start].decode('utf-8')
            raise DomainError('context_binary_unsupported', 415) from None

    def _read(self, row, relative_path, limit, budget=None):
        fd = self._open(row, relative_path)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise DomainError('context_not_file', 400)
            raw = os.read(fd, limit + 1)
            if budget is not None:
                budget[0] -= len(raw)
            after = os.fstat(fd)
            if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                raise DomainError('context_file_changed', 409)
            truncated = len(raw) > limit
            text = self._text(raw[:limit], truncated)
            # Reopen validates current ancestors, root identity and ignore policy.
            check = self._open(row, relative_path)
            try:
                current = os.fstat(check)
                if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
                    raise DomainError('context_file_changed', 409)
            finally:
                os.close(check)
            self._recheck(row)
            return {'relative_path': relative_path, 'text': text, 'truncated': truncated, 'trust': 'untrusted'}
        finally:
            os.close(fd)

    def read(self, source_id, relative_path=''):
        row = self._row(source_id)
        return self._read(row, relative_path, self.max_read_bytes)

    def list(self, source_id, relative_path=''):
        row = self._row(source_id)
        fd = self._open(row, relative_path)
        entries = []
        truncated = False
        try:
            if not stat.S_ISDIR(os.fstat(fd).st_mode):
                raise DomainError('context_not_directory', 400)
            # scandir is lazy: do not materialize an arbitrarily large directory.
            with os.scandir(fd) as iterator:
                for scanned, entry in enumerate(iterator):
                    if scanned >= 2000 or len(entries) >= self.max_entries:
                        truncated = True
                        break
                    path = '/'.join(filter(None, (relative_path, entry.name)))
                    try:
                        child = self._open(row, path)
                    except DomainError:
                        continue
                    try:
                        info = os.fstat(child)
                        entries.append({'name': entry.name, 'relative_path': path,
                                        'kind': 'directory' if stat.S_ISDIR(info.st_mode) else 'file'})
                    finally:
                        os.close(child)
            self._recheck(row)
            return {'entries': sorted(entries, key=lambda e: e['name']), 'truncated': truncated, 'trust': 'untrusted'}
        except OSError:
            raise DomainError('context_path_unavailable', 403) from None
        finally:
            os.close(fd)

    def search(self, source_id, query, relative_path=''):
        if not isinstance(query, str) or not query.strip() or len(query) > 256 or '\x00' in query:
            raise DomainError('invalid_context_query', 400)
        row = self._row(source_id)
        self._parts(relative_path)
        queue = [relative_path]
        matches = []
        budget = [self.max_search_bytes]
        operations = 0
        truncated = False
        deadline = time.monotonic() + 3
        while queue:
            if operations >= 500 or budget[0] <= 0 or time.monotonic() >= deadline:
                truncated = True
                break
            path = queue.pop()
            operations += 1
            try:
                fd = self._open(row, path)
                try:
                    is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
                finally:
                    os.close(fd)
                if is_directory:
                    listing = self.list(source_id, path)
                    truncated |= listing['truncated']
                    queue.extend(entry['relative_path'] for entry in reversed(listing['entries']))
                    continue
                read_limit = min(max(0, budget[0] - 1), self.max_read_bytes)
                # Charge actual bytes even when decoding rejects the evidence.
                read = self._read(row, path, read_limit, budget)
                truncated |= read['truncated']
                for number, line in enumerate(read['text'].splitlines(), 1):
                    if query.casefold() in line.casefold():
                        matches.append({'relative_path': path, 'line': number, 'text': line[:1000]})
                        if len(matches) >= self.max_results:
                            truncated = True
                            break
                if len(matches) >= self.max_results:
                    break
            except DomainError as error:
                if error.code in {'context_source_revoked', 'context_permission_changed', 'context_source_changed'}:
                    raise
                continue
        self._recheck(row)
        return {'matches': matches, 'truncated': truncated, 'trust': 'untrusted'}
