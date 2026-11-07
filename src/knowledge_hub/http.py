"""Loopback HTTP adapter for the canonical store."""
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .store import Store
from .retrieval import Retrieval, DEFAULT_CHARS
from .core import ProjectCreate, Proposal, DomainError

from .version import VERSION
WEB_DIR = Path(__file__).parent / 'web'


def create_app(data_dir: Path, human_token: str, agent_token: str) -> FastAPI:
    if not human_token or not agent_token or secrets.compare_digest(human_token, agent_token):
        raise ValueError('distinct_nonempty_tokens')
    app = FastAPI(title='Knowledge Hub', version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    store = Store(data_dir)
    app.state.store = store
    sessions: set[str] = set()
    from .shared_http import register as register_shared
    register_shared(app, store)

    @app.middleware('http')
    async def authentication(request: Request, call_next):
        host = request.headers.get('host', '')
        try:
            parsed = urlsplit('http://' + host)
            valid_host = (parsed.hostname in {'localhost', '127.0.0.1', '::1', 'testserver'}
                          and not parsed.username and not parsed.password and not parsed.path
                          and not parsed.query and not parsed.fragment)
            parsed.port
        except ValueError:
            valid_host = False
        if not valid_host:
            return JSONResponse({'error': 'invalid_host'}, status_code=400)
        origin = request.headers.get('origin')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and origin is not None and origin != f'{request.url.scheme}://{host}':
            return JSONResponse({'error': 'foreign_origin'}, status_code=403)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'error': 'foreign_origin'}, status_code=403)
        path = request.url.path
        supplied = request.headers.get('authorization', '')
        request.state.human = not supplied and request.cookies.get('kh_session') in sessions
        if path == '/api/session':
            if not secrets.compare_digest(supplied.encode('utf-8'), f'Bearer {human_token}'.encode('utf-8')):
                return JSONResponse({'error': 'authentication_required'}, status_code=401)
        elif path.startswith('/api/') and path != '/api/health':
            if not request.state.human and not secrets.compare_digest(supplied.encode('utf-8'), f'Bearer {agent_token}'.encode('utf-8')):
                return JSONResponse({'error': 'authentication_required'}, status_code=401)
        response = await call_next(request)
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/api/session')
    def session():
        token = secrets.token_urlsafe(32)
        sessions.add(token)
        response = JSONResponse({'status': 'authenticated'})
        response.set_cookie('kh_session', token, httponly=True, samesite='strict', path='/api')
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({'error': error.code}, status_code=error.status)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'version': VERSION}

    @app.get('/api/projects')
    def projects():
        return {'projects': store.projects()}

    @app.post('/api/projects')
    def create_project(command: ProjectCreate):
        return store.create_project(command.name, command.purpose)

    @app.get('/api/projects/{project_id}/agent/knowledge/{item_id}')
    def agent_item(project_id: str, item_id: str, max_chars: int = DEFAULT_CHARS, body_offset: int = 0, expected_revision: int | None = None):
        return Retrieval(store).get(project_id, item_id, max_chars, body_offset, expected_revision)

    @app.get('/api/projects/{project_id}/agent/context')
    def agent_context(project_id: str, q: str = '', item_ids: list[str] = Query(default=[]), max_chars: int = DEFAULT_CHARS, cursor: str = ''):
        return Retrieval(store).context(project_id, q, item_ids, max_chars, cursor)

    @app.get('/api/projects/{project_id}/agent/search')
    def agent_search(project_id: str, q: str = '', state: str = '', max_chars: int = DEFAULT_CHARS, cursor: str = ''):
        return Retrieval(store).search(project_id, q, state, max_chars, cursor)

    @app.get('/api/projects/{project_id}/knowledge')
    def knowledge(project_id: str, q: str = '', state: str = ''):
        return store.knowledge(project_id, q, state)

    @app.get('/api/projects/{project_id}/knowledge/{item_id}')
    def item(project_id: str, item_id: str):
        return store.get_item(project_id, item_id)

    @app.get('/api/projects/{project_id}/context')
    def context(project_id: str):
        return store.context(project_id)

    @app.get('/api/projects/{project_id}/changes')
    def changes(project_id: str):
        return {'changes': store.changes(project_id)}

    @app.post('/api/projects/{project_id}/changes')
    def propose(project_id: str, command: Proposal):
        return store.propose(project_id, command)

    @app.post('/api/projects/{project_id}/changes/{change_id}/approve')
    def approve(project_id: str, change_id: str, request: Request):
        if not request.state.human:
            raise DomainError('approval_required', 403)
        return store.approve(project_id, change_id)

    @app.post('/api/projects/{project_id}/changes/{change_id}/reject')
    def reject(project_id: str, change_id: str, request: Request):
        if not request.state.human:
            raise DomainError('approval_required', 403)
        return store.reject(project_id, change_id)

    @app.get('/')
    def reader():
        if not (WEB_DIR / 'index.html').is_file():
            return JSONResponse({'error': 'reader_assets_unavailable'}, status_code=503)
        return FileResponse(WEB_DIR / 'index.html')

    from .library_http import register as register_library
    from .intake_http import register as register_intake
    from .updater_http import register as register_updates
    register_library(app, store)
    register_intake(app, store)
    register_updates(app, store)
    from .connections_http import register as register_connections
    register_connections(app, store)
    from .context_sources_http import register as register_context_sources
    register_context_sources(app, data_dir)
    from .curator_jobs_http import register as register_curator_jobs
    register_curator_jobs(app, store)
    from contextlib import asynccontextmanager
    import asyncio
    import threading
    from .curator_jobs import CuratorJobWorker

    @asynccontextmanager
    async def lifespan(application):
        stop = threading.Event()
        worker = CuratorJobWorker(application.state.curator_jobs)
        thread = threading.Thread(target=worker.run, args=(stop,),
                                  name='knowledge-hub-curator', daemon=False)
        application.state.curator_job_stop = stop
        application.state.curator_job_thread = thread
        thread.start()
        try:
            yield
        finally:
            stop.set()
            await asyncio.to_thread(thread.join, 5)
            if thread.is_alive():
                raise RuntimeError('Curator worker did not stop; shutdown is incomplete')

    app.router.lifespan_context = lifespan
    app.mount('/assets', StaticFiles(directory=WEB_DIR, check_dir=False), name='assets')
    return app
