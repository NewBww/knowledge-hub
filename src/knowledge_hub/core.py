"""Typed shared commands; knowledge bodies are inert plain text."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default='', max_length=4000)


class Evidence(StrictModel):
    kind: Literal['user_decision', 'document', 'observation']
    locator: str = Field(max_length=4000)
    label: str = Field(max_length=1000)


class Upsert(StrictModel):
    op: Literal['upsert']
    id: UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(max_length=100000)
    kind: Literal['fact', 'finding', 'concept', 'procedure', 'decision', 'question']
    evidence: list[Evidence] = Field(default_factory=list, max_length=100)
    depends_on: list[UUID] = Field(default_factory=list, max_length=1000)


class Proposal(StrictModel):
    base_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    operations: list[Upsert] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_items(self):
        identifiers = [operation.id for operation in self.operations if operation.id is not None]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError('duplicate_item')
        return self


class DomainError(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code = code
        self.status = status
        super().__init__(code)
