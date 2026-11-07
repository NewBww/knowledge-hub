"""Typed library projections. Canonical knowledge is referenced, never upserted here."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator
from .core import StrictModel


class Support(StrictModel):
    item_id: UUID
    revision: int = Field(ge=1)
    relationship: Literal['supports', 'prerequisite', 'qualifies'] = 'supports'


class Section(StrictModel):
    id: UUID
    kind: Literal['factual', 'editorial']
    body: str = Field(max_length=100000)
    supports: list[Support] = Field(default_factory=list, max_length=1000)


class PageUpsert(StrictModel):
    op: Literal['upsert_page']
    id: UUID
    base_revision: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=500)
    state: Literal['draft', 'published', 'archived'] = 'draft'
    sections: list[Section] = Field(min_length=1, max_length=100)
    links: list[UUID] = Field(default_factory=list, max_length=1000)


class BookUpsert(StrictModel):
    op: Literal['upsert_book']
    id: UUID
    base_revision: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=500)
    purpose: str = Field(default='', max_length=4000)
    overview: str = Field(default='', max_length=10000)
    state: Literal['draft', 'published', 'archived'] = 'draft'
    page_ids: list[UUID] = Field(default_factory=list, max_length=1000)


class LibraryProposal(StrictModel):
    base_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    operations: list[Annotated[PageUpsert | BookUpsert, Field(discriminator='op')]] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_references(self):
        def unique(values):
            if len(values) != len(set(values)):
                raise ValueError('duplicate_reference')
        unique([op.id for op in self.operations])
        for op in self.operations:
            if isinstance(op, PageUpsert):
                unique([s.id for s in op.sections])
                unique(op.links)
                for section in op.sections:
                    unique([s.item_id for s in section.supports])
            else:
                unique(op.page_ids)
        return self
