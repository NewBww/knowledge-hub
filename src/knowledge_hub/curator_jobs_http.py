"""Human-session-only durable jobs. Mount behind existing Host/Origin/auth gates.

register() only registers routes; the desktop host must explicitly own a worker
and stop/join it on Quit. GETs reconnect to SQLite state, not an in-memory task.
"""
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from .core import StrictModel
from .curator_jobs import CuratorJobs, SubmitJob
from .intake_http import command, human


class Empty(StrictModel):
    pass


def register(app, store, *, jobs=None, sources=None, connections=None):
    if jobs is None:
        if sources is None:
            from .curator_jobs import ContextJobSources
            from .context_sources import ContextSources
            sources = ContextJobSources(ContextSources(store.path.parent))
        if connections is None:
            from .connections import Connections
            connections = getattr(app.state, 'connections', None) or Connections(store)
        jobs = CuratorJobs(store, sources=sources, connections=connections)
    app.state.curator_jobs = jobs

    @app.get('/api/curator-jobs')
    def listing(request: Request, status: str = '', cursor: str = '', limit: int = 20):
        human(request)
        return jobs.list(status=status, cursor=cursor, limit=limit)

    @app.get('/api/curator-jobs/{job_id}')
    def detail(job_id: str, request: Request):
        human(request)
        return jobs.get(job_id)

    @app.post('/api/curator-jobs')
    async def submit(request: Request):
        payload = await command(request, SubmitJob, 8192)
        return await run_in_threadpool(jobs.submit, payload.source_ids, payload.instruction,
                                      payload.request_id, human=True)

    @app.post('/api/curator-jobs/{job_id}/cancel')
    async def cancel(job_id: str, request: Request):
        await command(request, Empty, 1024)
        return await run_in_threadpool(jobs.cancel, job_id, human=True)

    @app.post('/api/curator-jobs/{job_id}/retry')
    async def retry(job_id: str, request: Request):
        await command(request, Empty, 1024)
        return await run_in_threadpool(jobs.retry, job_id, human=True)

    return jobs
