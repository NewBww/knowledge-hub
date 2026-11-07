"""Bounded local queue services for the user's own external MCP harness.

No provider clients, credentials, model execution or harness commands.
"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import secrets
from pydantic import ConfigDict, Field
from .core import DomainError, StrictModel, Upsert, Evidence, Proposal
from .intake import Intake, data_lock, fingerprint
from .privacy import AgentAccess
from .intake_models import MAX_FILE


class CurationOperation(Upsert):
    evidence: list[Evidence] = Field(default_factory=list, max_length=99)


class LibrarySuggestion(StrictModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    book_title: str = Field(min_length=1, max_length=500)
    page_title: str = Field(min_length=1, max_length=500)
    body: str = Field(max_length=20000)


class CurationSubmission(StrictModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    claim_token: str = Field(min_length=1, max_length=100)
    base_revision: int = Field(ge=0)
    summary: str = Field(min_length=1, max_length=4000)
    operations: list[CurationOperation] = Field(min_length=1, max_length=20)
    library_suggestions: list[LibrarySuggestion] = Field(default_factory=list, max_length=20)


def metadata(capture):
    result = {key: capture[key] for key in ('id', 'project_id', 'snapshot_sha256', 'expires_at', 'status')}
    result['files'] = [{key: value for key, value in file.items() if key != 'text'} for file in capture['files']]
    if capture.get('claim'):
        result['claim'] = {key: value for key, value in capture['claim'].items() if key != 'claim_token'}
    return result


def bounded(value, minimum, maximum, code='invalid_retrieval_limit'):
    if type(value) is not int or not minimum <= value <= maximum:
        raise DomainError(code, 422)


class Curator:
    def __init__(self, store):
        self.store = store
        self.intake = Intake(store)
        self.access = AgentAccess(store)

    def set_agent_access(self, project_id, enabled):
        """Human-only adapter boundary; never expose this method as an agent tool."""
        return self.access.set(project_id, enabled)

    def agent_access(self, project_id):
        return self.access.get(project_id)

    def capture_list(self, project_id, limit=20, offset=0):
        with data_lock(self.store.path.parent):
            self.access.require(project_id)
            bounded(limit, 1, 100)
            bounded(offset, 0, 2**31 - 1)
            captures = self.intake.list(project_id)
            end = min(offset + limit, len(captures))
            return {'captures': captures[offset:end], 'total': len(captures),
                    'next_offset': end if end < len(captures) else None}

    def _revision(self, project_id):
        project = next((project for project in self.store.projects() if project['id'] == project_id), None)
        if project is None:
            raise DomainError('project_not_found', 404)
        return project['revision']

    def claim(self, project_id, capture_id, claimant, snapshot_sha256, base_revision, ttl_seconds=300):
        with data_lock(self.store.path.parent):
            self.access.require(project_id)
            bounded(base_revision, 0, 2**63 - 1, 'invalid_base_revision')
            bounded(ttl_seconds, 30, 900, 'invalid_claim_ttl')
            if not isinstance(claimant, str) or not 1 <= len(claimant) <= 100 or not claimant.strip() or any(ord(c) < 32 for c in claimant):
                raise DomainError('invalid_claimant', 422)
            capture = self.intake.get(project_id, capture_id)
            if capture['status'] != 'pending_agent' or capture.get('submission_sha256'):
                raise DomainError('capture_already_proposed')
            if snapshot_sha256 != capture['snapshot_sha256']:
                raise DomainError('capture_snapshot_mismatch')
            if base_revision != self._revision(project_id):
                raise DomainError('stale_revision')
            now = datetime.now(timezone.utc)
            existing = capture.get('claim')
            if existing and datetime.fromisoformat(existing['expires_at']) > now:
                raise DomainError('capture_claimed')
            lease = {'claim_token': str(uuid4()), 'expires_at': (now + timedelta(seconds=ttl_seconds)).isoformat(),
                     'base_revision': base_revision}
            capture['claim'] = {**lease, 'claimant': claimant}
            self.intake.save(capture)
            return lease

    def curation_submit(self, project_id, capture_id, submission: CurationSubmission):
        with data_lock(self.store.path.parent):
            self.access.require(project_id)
            try:
                # Revalidate even constructed/copied model instances at the service boundary.
                submission = CurationSubmission.model_validate(submission.model_dump(mode='json') if isinstance(submission, CurationSubmission) else submission)
            except (ValueError, TypeError):
                raise DomainError('invalid_curation_submission', 422) from None
            capture = self.intake.get(project_id, capture_id)
            digest = fingerprint(submission.model_dump(mode='json'))
            accepted = capture.get('submission_sha256')
            if accepted and accepted != digest:
                raise DomainError('idempotency_conflict')
            if capture.get('result'):
                return capture['result']
            if submission.snapshot_sha256 != capture['snapshot_sha256']:
                raise DomainError('capture_snapshot_mismatch')
            if not accepted:
                lease = capture.get('claim')
                if (not lease or not secrets.compare_digest(lease['claim_token'].encode(), submission.claim_token.encode())
                        or datetime.fromisoformat(lease['expires_at']) <= datetime.now(timezone.utc)):
                    raise DomainError('invalid_or_expired_claim')
                if submission.base_revision != lease['base_revision'] or submission.base_revision != self._revision(project_id):
                    raise DomainError('stale_revision')
            operations = []
            for operation in submission.operations:
                data = operation.model_dump(mode='json')
                data['evidence'].append({'kind': 'document', 'locator': 'capture:' + capture_id + '#' + capture['snapshot_sha256'],
                                         'label': 'External-agent curated capture; raw source may expire'})
                operations.append(data)
            try:
                proposal = Proposal(base_revision=submission.base_revision, idempotency_key='capture:' + capture_id,
                                    summary=submission.summary, operations=operations)
            except ValueError:
                raise DomainError('invalid_curation_submission', 422) from None
            # Bind the entire authorized submission (including local suggestions)
            # before crossing the separate SQLite commit / manifest-save boundary.
            # An exact retry is completion of this accepted work, not a new lease.
            if not accepted:
                capture['submission_sha256'] = digest
                self.intake.save(capture)
            change = self.store.propose(project_id, proposal)
            result = {'warehouse_change': change, 'library_suggestions': [suggestion.model_dump() for suggestion in submission.library_suggestions]}
            capture['status'] = 'proposed'
            capture['submission_sha256'] = digest
            capture['result'] = result
            self.intake.save(capture)
            return result

    def capture_get(self, project_id, capture_id, source_id='paste', offset=0, max_chars=12000,
                    attachment_id=None, byte_offset=0, max_bytes=1048576):
        with data_lock(self.store.path.parent):
            self.access.require(project_id)
            bounded(max_chars, 1, 20000)
            bounded(offset, 0, 2**31 - 1)
            bounded(max_bytes, 1, 1048576)
            bounded(byte_offset, 0, 2**31 - 1)
            capture = self.intake.get(project_id, capture_id)
            result = {**metadata(capture), 'intent': capture['intent']}
            if capture.get('request_context') is not None:
                result['request_context'] = capture['request_context']
            if attachment_id is not None:
                file = next((file for file in capture['files'] if file['id'] == attachment_id), None)
                if file is None:
                    raise DomainError('attachment_not_found', 404)
                path = self.intake._directory(capture_id) / file['id']
                if path.is_symlink():
                    raise DomainError('unsafe_local_storage')
                with path.open('rb') as stream:
                    data = stream.read(MAX_FILE + 1)
                if len(data) != file['size'] or hashlib.sha256(data).hexdigest() != file['sha256']:
                    raise DomainError('capture_integrity_error')
                chunk = data[byte_offset:byte_offset + max_bytes]
                end = byte_offset + len(chunk)
                result['attachment'] = {'id': file['id'], 'media_type': file['media_type'], 'sha256': file['sha256'],
                                        'total_bytes': len(data), 'byte_offset': byte_offset,
                                        'content_base64': base64.b64encode(chunk).decode(),
                                        'next_byte_offset': end if end < len(data) else None}
                return result
            if source_id == 'paste':
                text = capture['text']
            else:
                file = next((file for file in capture['files'] if file['id'] == source_id), None)
                if file is None:
                    raise DomainError('source_not_found', 404)
                text = file['text']
            chunk = text[offset:offset + max_chars]
            end = offset + len(chunk)
            return {**result, 'source_id': source_id, 'text': chunk, 'offset': offset,
                    'total_chars': len(text), 'next_offset': end if end < len(text) else None}
