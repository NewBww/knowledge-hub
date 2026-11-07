"""Nonsecret account registry; active projection preserves the Curator contract."""
import hashlib
import json
import secrets
from pathlib import Path
from .core import DomainError
from .intake import data_lock, private_write

# Auth route and inference destination are intentionally separate identities.
ROUTES = {
    'openrouter_api_key': ('openrouter', 'OpenRouter API key', 'https://openrouter.ai'),
    'openrouter_oauth': ('openrouter', 'OpenRouter OAuth', 'https://openrouter.ai'),
    'chatgpt_oauth': ('chatgpt', 'ChatGPT OAuth (Codex app-server)', 'OpenAI via Codex app-server'),
    'codex_cli': ('chatgpt', 'Codex CLI', 'OpenAI via Codex CLI'),
    'copilot_cli': ('copilot', 'GitHub Copilot CLI', 'GitHub Copilot'),
    'opencode_cli': ('opencode', 'OpenCode CLI', 'Configured OpenCode provider'),
    'gemini_cli': ('gemini', 'Gemini CLI', 'Google Gemini'),
    'nous_proxy': ('hermes', 'Nous subscription proxy', 'Nous via Hermes proxy'),
    'hermes_agent_cli': ('hermes', 'Hermes Agent CLI', 'Configured Hermes provider'),
}
LEGACY_ROUTES = {'openrouter': 'openrouter_oauth', 'chatgpt': 'codex_cli', 'copilot': 'copilot_cli',
                 'opencode': 'opencode_cli', 'gemini': 'gemini_cli', 'hermes': 'nous_proxy'}

class ProfileConnections:
    def _raw(self):
        if self.path.is_symlink():
            raise DomainError('unsafe_local_storage')
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text())
            if not isinstance(value, dict): raise ValueError()
            return value
        except (ValueError, OSError):
            raise DomainError('invalid_configuration') from None

    def _registry(self):
        raw = self._raw()
        if raw.get('version') == 2:
            return raw
        if raw.get('connection'):
            # Keep ownership of the original Keychain item and original CLI home.
            profile = {**raw, 'profile_id': 'legacy', 'name': 'Saved connection',
                       'auth_route': LEGACY_ROUTES[raw['connection']], 'legacy_credentials': True}
            return {'version': 2, 'active_profile_id': 'legacy', 'profiles': {'legacy': profile}}
        return {'version': 2, 'active_profile_id': None, 'profiles': {},
                **({'staged': raw['staged']} if raw.get('staged') else {})}

    def _write_registry(self, value):
        if self.path.is_symlink(): raise DomainError('unsafe_local_storage')
        private_write(self.path, json.dumps(value).encode())

    def profiles(self):
        with data_lock(self.root):
            registry = self._registry()
            return {'active_profile_id': registry['active_profile_id'],
                    'profiles': [{k: v for k, v in profile.items() if k != 'legacy_credentials'}
                                 for profile in registry['profiles'].values()]}

    def add_profile(self, auth_route, name, *, human=False):
        from .connections import require_human
        require_human(human)
        if auth_route not in ROUTES or not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise DomainError('invalid_configuration', 422)
        with data_lock(self.root):
            registry = self._registry()
            if len(registry['profiles']) >= 50: raise DomainError('connection_limit', 409)
            profile_id = secrets.token_hex(16)
            profile = {'profile_id': profile_id, 'name': name.strip(), 'auth_route': auth_route,
                       'connection': ROUTES[auth_route][0], 'model': None, 'consent': True,
                       'enabled': False, 'status': 'sign_in_required', 'last_error': None,
                       'generation': secrets.token_hex(16)}
            registry['profiles'][profile_id] = profile
            registry['active_profile_id'] = profile_id
            self._write_registry(registry)
            return self.state()

    def activate_profile(self, profile_id, *, human=False):
        from .connections import require_human
        require_human(human)
        with data_lock(self.root):
            registry = self._registry()
            if profile_id not in registry['profiles']: raise DomainError('connection_not_found', 404)
            profile = registry['profiles'][profile_id]
            profile.update(generation=secrets.token_hex(16), enabled=False, status='unchecked', last_error=None)
            registry['active_profile_id'] = profile_id
            self._write_registry(registry)
            return self.state()

    def profile_root(self, state):
        if state.get('legacy_credentials') or not state.get('profile_id'): return self.root
        directory = self.root / 'connection-profiles' / state['profile_id']
        if any(path.is_symlink() for path in [directory, *directory.parents]):
            raise DomainError('unsafe_local_storage')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        return directory

    def route_catalog(self):
        return [{'id': route, 'connection': values[0], 'name': values[1], 'destination': values[2],
                 'availability': 'unsupported_capability' if route == 'hermes_agent_cli' else
                    'integration_required' if route == 'chatgpt_oauth' else 'sign_in_required',
                 'model_discovery': 'authenticated_catalog' if route.startswith('openrouter_') else 'unsupported',
                 'reason': ('Native Sign in with ChatGPT requires registered app credentials; official Codex app-server login is a separate integration.'
                            if route == 'chatgpt_oauth' else
                            'Tool-denial contract is not verified; no agent execution is allowed.' if route == 'hermes_agent_cli' else '')}
                for route, values in ROUTES.items()]

    def start_profile_auth(self, profile_id, *, human=False, callback_url=None):
        from .connections import require_human, PRESETS
        require_human(human)
        with data_lock(self.root):
            state = self._load()
            if state.get('profile_id') != profile_id: raise DomainError('configuration_changed', 409)
            route = state['auth_route']
            if route in {'chatgpt_oauth', 'hermes_agent_cli'}: raise DomainError('unsupported_capability', 409)
            if route == 'openrouter_api_key':
                return {'status': 'api_key_required', 'profile_id': profile_id}
            if route == 'openrouter_oauth':
                return self.start_auth('openrouter', human=True, callback_url=callback_url)
            from .cli_auth import auth_handoff
            connection = state['connection']
            _, executable, guide, command = PRESETS[connection]
            return auth_handoff(self.profile_root(state), connection, self.discover(executable), guide, command)

    def set_profile_key(self, profile_id, key, *, human=False):
        from .connections import require_human
        require_human(human)
        with data_lock(self.root):
            state = self._load()
            if not profile_id or state.get('profile_id') != profile_id:
                raise DomainError('configuration_changed', 409)
            return self.set_key(state['connection'], key, human=True)

    def model_listing(self, route, key, root):
        from .model_discovery import discover_models
        return discover_models(route, key, root)

    def discover_models(self, profile_id, *, human=False):
        from .connections import require_human
        require_human(human)
        with data_lock(self.root):
            state = self._load()
            if not profile_id or state.get('profile_id') != profile_id:
                raise DomainError('configuration_changed', 409)
            generation = state['generation']
            route = state['auth_route']
            key = self._vault().get(self.credential_name(profile_id)) if state['connection'] == 'openrouter' else None
            if state['connection'] == 'openrouter' and not key:
                raise DomainError('sign_in_required', 403)
            root = self.profile_root(state)
        result = self.model_listing(route, key, root)
        # Validate every pin, even when the provider catalogue is malformed.
        from .connections import configuration
        models = []
        seen = set()
        for item in result['models']:
            try:
                model = configuration({'connection': state['connection'], 'model': item['id']})['model']
            except (DomainError, KeyError, TypeError):
                continue
            if model not in seen:
                models.append({'id': model, 'name': str(item.get('name') or model)[:200]})
                seen.add(model)
        if len(models) > 5000: raise DomainError('invalid_provider_response', 502)
        with data_lock(self.root):
            current = self._load()
            if current.get('profile_id') != profile_id or current.get('generation') != generation:
                raise DomainError('configuration_changed', 409)
            current['discovered_models'] = {'models': models, 'source': result['source'],
                'availability': result['availability'], 'generation': generation}
            self._save(current)
            return {**current['discovered_models'], 'profile_id': profile_id}

    def select_model(self, profile_id, model, *, human=False):
        from .connections import require_human
        require_human(human)
        with data_lock(self.root):
            state = self._load()
            if state.get('profile_id') != profile_id: raise DomainError('configuration_changed', 409)
            discovered = state.get('discovered_models', {})
            if discovered.get('generation') != state.get('generation'):
                raise DomainError('model_discovery_required', 409)
            if model not in {item['id'] for item in discovered.get('models', [])}:
                raise DomainError('model_not_discovered', 422)
            generation = secrets.token_hex(16)
            discovered['generation'] = generation
            state.update(model=model, generation=generation, status='unchecked', enabled=False, last_error=None)
            self._save(state)
            return self.state()

    def credential_name(self, profile_id=None):
        base = 'knowledge-hub-curator-' + hashlib.sha256(str(self.root.resolve()).encode()).hexdigest()
        with data_lock(self.root):
            registry = self._registry()
            profile_id = profile_id or registry['active_profile_id']
            if profile_id:
                profile = registry['profiles'].get(profile_id)
                if profile is None: raise DomainError('connection_not_found', 404)
                if not profile.get('legacy_credentials'): return base + '-' + profile_id
            return base
