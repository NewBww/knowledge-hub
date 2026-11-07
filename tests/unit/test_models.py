import pytest
from pydantic import ValidationError
from knowledge_hub.core import Proposal


def test_proposal_rejects_self_approval_and_normalizes_operations():
    with pytest.raises(ValidationError):
        Proposal(base_revision=0, idempotency_key='key', summary='test', operations=[], approved=True)
    proposal = Proposal(base_revision=0, idempotency_key='key', summary='test', operations=[
        {'op': 'upsert', 'title': 'Synthetic fact', 'body': 'Plain text', 'kind': 'fact'}])
    assert proposal.operations[0].depends_on == []
    assert proposal.operations[0].evidence == []
    with pytest.raises(ValidationError):
        Proposal(base_revision=-1, idempotency_key='key', summary='test', operations=[])


def test_duplicate_operations_rejected():
    from uuid import uuid4
    identifier = str(uuid4())
    operation = {'op':'upsert', 'id':identifier, 'title':'Synthetic', 'body':'Only fixture', 'kind':'fact'}
    with pytest.raises(ValidationError, match='duplicate_item'):
        Proposal(base_revision=0, idempotency_key='key', summary='Duplicate', operations=[operation, operation])

