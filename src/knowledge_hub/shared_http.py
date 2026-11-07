"""Project-free HTTP adapter; uses the existing app authentication middleware."""
from fastapi import Request, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import Field
from .core import Proposal, StrictModel
from .shared import SharedWarehouse, public
from .library import Library
from .library_models import LibraryProposal
from .intake import Intake
from .intake_models import CaptureInput, MAX_BODY
from .curator import Curator
from .retrieval import Retrieval, DEFAULT_CHARS
from .intake_http import Finish, command, human


class Access(StrictModel):
    enabled: bool = Field(strict=True)


def register(app, store):
    shared = SharedWarehouse(store)
    scope = shared.scope()
    library, intake, curator = Library(store), Intake(store), Curator(store)
    app.state.warehouse = shared

    @app.get('/api/agent/search')
    def agent_search(q: str = '', state: str = '', max_chars: int = DEFAULT_CHARS, cursor: str = ''):
        return public(Retrieval(store).search(scope, q, state, max_chars, cursor))

    @app.get('/api/agent/context')
    def agent_context(q: str = '', item_ids: list[str] = Query(default=[]), max_chars: int = DEFAULT_CHARS, cursor: str = ''):
        return public(Retrieval(store).context(scope, q, item_ids, max_chars, cursor))

    @app.get('/api/agent/knowledge/{item_id}')
    def agent_item(item_id: str, max_chars: int = DEFAULT_CHARS, body_offset: int = 0, expected_revision: int | None = None):
        return public(Retrieval(store).get(scope, item_id, max_chars, body_offset, expected_revision))

    @app.middleware('http')
    async def no_legacy_partitions(request: Request, call_next):
        if request.url.path == '/api/projects' or request.url.path.startswith('/api/projects/'):
            return JSONResponse({'error': 'project_routes_removed', 'replacement': '/api/workspace'},
                                status_code=410, headers={'Deprecation': 'true', 'Cache-Control': 'no-store'})
        return await call_next(request)

    @app.get('/api/workspace')
    def workspace():
        return shared.state()

    @app.get('/api/warehouse')
    def knowledge(q: str = '', state: str = ''):
        return public(store.knowledge(scope, q, state))

    @app.get('/api/warehouse/{item_id}')
    def item(item_id: str):
        return public(store.get_item(scope, item_id))

    @app.get('/api/changes')
    def changes():
        return public({'changes': store.changes(scope)})

    @app.post('/api/changes')
    def propose(payload: Proposal):
        return public(store.propose(scope, payload))

    @app.post('/api/changes/{change_id}/approve')
    def approve(change_id: str, request: Request):
        human(request)
        return public(store.approve(scope, change_id))

    @app.post('/api/changes/{change_id}/reject')
    def reject(change_id: str, request: Request):
        human(request)
        return public(store.reject(scope, change_id))

    @app.get('/api/library/books')
    def books():
        return public({'books': library.books(scope)})

    @app.get('/api/library/books/{book_id}')
    def book(book_id: str):
        return public(library.book(scope, book_id))

    @app.get('/api/library/pages/{page_id}')
    def page(page_id: str):
        return public(library.page(scope, page_id))

    @app.get('/api/library/changes')
    def library_changes():
        return public({'changes': library.changes(scope)})

    @app.post('/api/library/changes')
    def propose_library(payload: LibraryProposal):
        return public(library.propose(scope, payload))

    @app.post('/api/library/changes/{change_id}/approve')
    def approve_library(change_id: str, request: Request):
        human(request)
        return public(library.approve(scope, change_id))

    @app.post('/api/library/changes/{change_id}/reject')
    def reject_library(change_id: str, request: Request):
        human(request)
        return public(library.reject(scope, change_id))

    @app.get('/api/agent/access')
    def access(request: Request):
        value = curator.agent_access(scope)
        return {'enabled': value['agent_access'], 'limitation': value['limitation']}

    @app.post('/api/agent/access')
    async def set_access(request: Request):
        payload = await command(request, Access, 1024)
        value = await run_in_threadpool(curator.set_agent_access, scope, payload.enabled)
        return {'enabled': value['agent_access'], 'limitation': value['limitation']}

    @app.get('/api/captures')
    def captures(request: Request, limit: int = 20, offset: int = 0):
        if not request.state.human:
            return public(curator.capture_list(scope, limit, offset))
        return public({'captures': intake.list(scope)})

    @app.post('/api/captures')
    async def create_capture(request: Request):
        payload = await command(request, CaptureInput, MAX_BODY)
        return public(await run_in_threadpool(intake.create, scope, payload))

    @app.get('/api/captures/{capture_id}')
    def capture(capture_id: str, request: Request, source_id: str = 'paste', offset: int = 0,
                max_chars: int = 12000, attachment_id: str | None = None, byte_offset: int = 0, max_bytes: int = 1048576):
        if not request.state.human:
            return public(curator.capture_get(scope, capture_id, source_id, offset, max_chars, attachment_id, byte_offset, max_bytes))
        return public(intake.get(scope, capture_id))

    @app.delete('/api/captures/{capture_id}')
    def delete(capture_id: str, request: Request):
        human(request)
        return intake.delete(scope, capture_id)

    @app.post('/api/captures/{capture_id}/finish')
    async def finish(capture_id: str, request: Request):
        payload = await command(request, Finish, 1024)
        if payload.retain_source:
            return {'status': 'retained_until_expiry', 'expires_at': intake.get(scope, capture_id)['expires_at']}
        return intake.delete(scope, capture_id)
