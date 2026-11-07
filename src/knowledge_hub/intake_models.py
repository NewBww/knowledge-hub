"""Strict capture wire models. Uploaded names are labels, never paths to open."""
from pydantic import Field, model_validator
from .core import StrictModel

MAX_FILE = 5 * 1024 * 1024
MAX_TOTAL = 20 * 1024 * 1024
MAX_BODY = 29 * 1024 * 1024


class Upload(StrictModel):
    name: str = Field(min_length=1, max_length=240)
    media_type: str = Field(min_length=1, max_length=120)
    content_base64: str = Field(max_length=((MAX_FILE + 2) // 3) * 4)


class RequestContext(StrictModel):
    page_id: str = Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
    page_revision: int = Field(ge=1, strict=True)
    section_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
    passage: str = Field(min_length=1, max_length=10000)


class CaptureInput(StrictModel):
    text: str = Field(default='', max_length=100000)
    intent: str = Field(default='', max_length=4000)
    files: list[Upload] = Field(default_factory=list, max_length=20)
    request_context: RequestContext | None = None
    retention_days: int = Field(default=7, ge=1, le=30, strict=True)

    @model_validator(mode='after')
    def nonempty(self):
        if self.request_context is not None and self.intent not in {'request', 'Request something'}:
            raise ValueError('context_requires_request_intention')
        if not self.text.strip() and not self.files:
            raise ValueError('empty_capture')
        return self
