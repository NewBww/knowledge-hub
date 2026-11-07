"""Authenticated local human setup and a state-bound provider callback.

Register behind the app's Host/Origin/session middleware. Never expose a secret
field in MCP. Disable HTTP access logging of auth callback query strings in the
serving layer; authorization codes are short-lived but still sensitive.
"""
import logging
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import Field, SecretStr
from .core import StrictModel
from .connections import Connections, Configuration
from .curator_runtime import CuratorRuntime
from .intake_http import command, human


class ConfigCommand(StrictModel):
    configuration: Configuration
    confirm: bool = Field(default=False, strict=True)
    consent: bool = Field(default=False, strict=True)


class AuthStart(StrictModel):
    connection: str = Field(min_length=1, max_length=30)


class AuthComplete(StrictModel):
    state: str = Field(min_length=1, max_length=200)
    code: SecretStr


class Credential(StrictModel):
    connection: str = Field(min_length=1, max_length=30)
    key: SecretStr


class Enable(StrictModel):
    enabled: bool = Field(strict=True)


class SavedProfile(StrictModel):
    auth_route: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)


class ProfileTarget(StrictModel):
    profile_id: str = Field(min_length=1, max_length=64)


class ProfileModel(ProfileTarget):
    model: str = Field(min_length=1, max_length=200)


class ProfileKey(ProfileTarget):
    key: SecretStr


class Empty(StrictModel):
    pass


class AuthCallbackLogFilter(logging.Filter):
    """Uvicorn access records must not retain OAuth codes or state."""
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(value.split('?', 1)[0] if isinstance(value, str) and value.startswith('/curator-auth/callback?') else value
                                for value in record.args)
        return True


def register(app, store, *, connections=None, runtime=None):
    logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(item, AuthCallbackLogFilter) for item in logger.filters):
        logger.addFilter(AuthCallbackLogFilter())
    connections = connections or Connections(store)
    runtime = runtime or CuratorRuntime(store, connections)
    app.state.connections = connections
    app.state.curator_runtime = runtime
    app.state.runtime = runtime

    @app.get('/api/curator/profiles')
    def profiles():
        return connections.profiles()

    @app.post('/api/curator/profiles')
    async def add_profile(request: Request):
        payload = await command(request, SavedProfile, 2048)
        runtime.cancel()
        return await run_in_threadpool(connections.add_profile, payload.auth_route, payload.name, human=True)

    @app.post('/api/curator/profiles/activate')
    async def activate_profile(request: Request):
        payload = await command(request, ProfileTarget, 1024)
        runtime.cancel()
        return await run_in_threadpool(connections.activate_profile, payload.profile_id, human=True)

    @app.post('/api/curator/profiles/auth')
    async def profile_auth(request: Request):
        payload = await command(request, ProfileTarget, 1024)
        callback = str(request.base_url).rstrip('/') + '/curator-auth/callback'
        return await run_in_threadpool(connections.start_profile_auth, payload.profile_id, callback_url=callback, human=True)

    @app.post('/api/curator/profiles/key')
    async def profile_key(request: Request):
        payload = await command(request, ProfileKey, 8192)
        return await run_in_threadpool(connections.set_profile_key, payload.profile_id, payload.key.get_secret_value(), human=True)

    @app.post('/api/curator/profiles/models')
    async def profile_models(request: Request):
        payload = await command(request, ProfileTarget, 1024)
        return await run_in_threadpool(connections.discover_models, payload.profile_id, human=True)

    @app.post('/api/curator/profiles/model')
    async def profile_model(request: Request):
        payload = await command(request, ProfileModel, 2048)
        runtime.cancel()
        return await run_in_threadpool(connections.select_model, payload.profile_id, payload.model, human=True)

    @app.get('/api/curator/catalog')
    def catalog():
        return connections.catalog()

    @app.get('/api/curator')
    def state():
        return connections.state()

    @app.post('/api/curator/config')
    async def configure(request: Request):
        payload = await command(request, ConfigCommand, 4096)
        config = payload.configuration.model_dump()
        if payload.confirm:
            return await run_in_threadpool(connections.confirm, config, consent=payload.consent, human=True)
        return await run_in_threadpool(connections.stage, config)

    @app.post('/api/curator/auth/start')
    async def start_auth(request: Request):
        payload = await command(request, AuthStart, 1024)
        callback = str(request.base_url).rstrip('/') + '/curator-auth/callback'
        return await run_in_threadpool(connections.start_auth, payload.connection, callback_url=callback, human=True)

    @app.post('/api/curator/auth/complete')
    async def complete_auth(request: Request):
        payload = await command(request, AuthComplete, 8192)
        return await run_in_threadpool(connections.complete_auth, payload.state, payload.code.get_secret_value(), human=True)

    @app.get('/curator-auth/callback')
    async def callback(request: Request):
        # SameSite=Strict UI cookies do not accompany a cross-site OAuth redirect.
        # The one-use random state is created ONLY by human-authenticated start.
        # This non-API callback discloses nothing and cannot enable processing.
        await run_in_threadpool(connections.complete_auth, request.query_params.get('state', ''),
                                request.query_params.get('code', ''), human=True)
        return HTMLResponse('<!doctype html><meta charset="utf-8"><title>Curator sign-in</title>'
                            '<p>Sign-in complete. Return to Knowledge Hub Settings to check and enable Curator.</p>',
                            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})

    @app.post('/api/curator/auth/key')
    async def credential(request: Request):
        payload = await command(request, Credential, 8192)
        return await run_in_threadpool(connections.set_key, payload.connection, payload.key.get_secret_value(), human=True)

    @app.post('/api/curator/enable')
    async def enable(request: Request):
        payload = await command(request, Enable, 1024)
        if not payload.enabled:
            # Revocation must cancel a live subprocess before its pending write.
            runtime.cancel()
        result = await run_in_threadpool(connections.enable, payload.enabled, human=True)
        if payload.enabled:
            runtime.cancelled.clear()
        return result

    @app.post('/api/curator/check')
    async def check(request: Request):
        await command(request, Empty, 1024)
        return await run_in_threadpool(runtime.check, human=True)

    @app.post('/api/curator/run')
    async def run(request: Request):
        await command(request, Empty, 1024)
        return await run_in_threadpool(runtime.run_once, human=True)
