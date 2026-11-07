"""Human-session-only local source adapter. Grants have no HTTP endpoint."""
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from pydantic import Field

from .context_sources import ContextSources
from .core import StrictModel
from .intake_http import command, human


class RelativePath(StrictModel):
    relative_path: str = Field(default='', max_length=2048, strict=True)


class Search(RelativePath):
    query: str = Field(min_length=1, max_length=256, strict=True)


class Empty(StrictModel):
    pass


def register(app, data_dir):
    sources = ContextSources(data_dir)
    app.state.context_sources = sources

    @app.get('/api/context-sources')
    def index(request: Request):
        human(request)
        return {'sources': sources.sources()}

    @app.get('/api/context-sources/{source_id}')
    def detail(source_id: str, request: Request):
        human(request)
        return sources.get(source_id)

    @app.post('/api/context-sources/{source_id}/revoke')
    async def revoke(source_id: str, request: Request):
        await command(request, Empty, 128)
        return await run_in_threadpool(sources.revoke, source_id)

    @app.post('/api/context-sources/{source_id}/list')
    async def listing(source_id: str, request: Request):
        payload = await command(request, RelativePath, 4096)
        return await run_in_threadpool(sources.list, source_id, payload.relative_path)

    @app.post('/api/context-sources/{source_id}/read')
    async def read(source_id: str, request: Request):
        payload = await command(request, RelativePath, 4096)
        return await run_in_threadpool(sources.read, source_id, payload.relative_path)

    @app.post('/api/context-sources/{source_id}/search')
    async def search(source_id: str, request: Request):
        payload = await command(request, Search, 4096)
        return await run_in_threadpool(sources.search, source_id, payload.query, payload.relative_path)
