"""Human-only local capture/handoff HTTP adapter. No AI provider routes."""
import json
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from pydantic import Field
from .core import DomainError, StrictModel
from .intake import Intake
from .intake_models import CaptureInput, MAX_BODY
from .curator import Curator


class Finish(StrictModel):
    retain_source: bool = Field(strict=True)


class Access(StrictModel):
    agent_access: bool = Field(strict=True)


def human(request):
    if not getattr(request.state, 'human', False):
        raise DomainError('approval_required', 403)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


async def command(request, model, limit=16384):
    human(request)
    try:
        if int(request.headers.get('content-length', '0')) > limit:
            raise DomainError('request_size_limit', 413)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > limit:
                raise DomainError('request_size_limit', 413)
        return model.model_validate(strict_json(data.decode('utf-8')))
    except (ValueError, TypeError, RecursionError):
        raise DomainError('invalid_request', 422) from None


def register(app, store):
    intake = Intake(store)
    curator = Curator(store)

    @app.post('/api/projects/{project_id}/captures')
    async def create_capture(project_id: str, request: Request):
        payload = await command(request, CaptureInput, MAX_BODY)
        return await run_in_threadpool(intake.create, project_id, payload)

    # Static access route must precede the capture-id route.
    @app.get('/api/projects/{project_id}/captures/access')
    def access(project_id: str, request: Request):
        human(request)
        return curator.agent_access(project_id)

    @app.put('/api/projects/{project_id}/captures/access')
    async def set_access(project_id: str, request: Request):
        payload = await command(request, Access, 1024)
        return await run_in_threadpool(curator.set_agent_access, project_id, payload.agent_access)

    @app.get('/api/projects/{project_id}/captures')
    def captures(project_id: str, request: Request):
        human(request)
        return {'captures': intake.list(project_id)}

    @app.get('/api/projects/{project_id}/captures/{capture_id}')
    def capture(project_id: str, capture_id: str, request: Request):
        human(request)
        return intake.get(project_id, capture_id)

    @app.delete('/api/projects/{project_id}/captures/{capture_id}')
    def delete(project_id: str, capture_id: str, request: Request):
        human(request)
        return intake.delete(project_id, capture_id)

    @app.post('/api/projects/{project_id}/captures/{capture_id}/finish')
    async def finish(project_id: str, capture_id: str, request: Request):
        payload = await command(request, Finish, 1024)
        if payload.retain_source:
            return {'status': 'retained_until_expiry', 'expires_at': intake.get(project_id, capture_id)['expires_at']}
        return intake.delete(project_id, capture_id)
