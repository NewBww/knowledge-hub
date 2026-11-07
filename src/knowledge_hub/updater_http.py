"""Manual update status. Release hosting and signed installation are not configured."""
from fastapi import Request
from .core import DomainError
from .updater import Updater


def register(app, store):
    app.state.updater = Updater(app.version)

    def human(request):
        if not getattr(request.state, 'human', False):
            raise DomainError('approval_required', 403)

    async def no_arguments(request):
        human(request)
        async for chunk in request.stream():
            if chunk:
                raise DomainError('invalid_arguments', 422)

    @app.get('/api/updates')
    def status(request: Request):
        human(request)
        return app.state.updater.state()

    @app.post('/api/updates/check')
    async def check(request: Request):
        await no_arguments(request)
        return app.state.updater.check()

    @app.post('/api/updates/install')
    async def install(request: Request):
        await no_arguments(request)
        if app.state.updater.state()['configured']:
            raise DomainError('native_confirmation_required', 409)
        raise DomainError('update_source_unconfigured', 409)
