"""Redacted, approval-first Curator setup. No startup authentication or inference.

CLI choices deliberately fail closed until isolated auth + deny-all tool execution
has been verified for their installed version. CLI sign-in remains a human handoff;
we never read, copy or replay an external client's credentials.
"""
import json
import shutil
import base64
import hashlib
import secrets
import threading
import time
from urllib.parse import urlparse, urlencode
from typing import Literal
from pydantic import ConfigDict, Field
from .core import StrictModel, DomainError
from .intake import data_lock, private_write

PRESETS = {
    'chatgpt': ('ChatGPT', 'codex', 'https://developers.openai.com/codex/cli/', ['codex', 'login']),
    'copilot': ('GitHub Copilot', 'copilot', 'https://docs.github.com/copilot/how-tos/copilot-cli', ['copilot', 'login']),
    'openrouter': ('OpenRouter', None, 'https://openrouter.ai/docs/guides/overview/auth/oauth', []),
    'opencode': ('OpenCode', 'opencode', 'https://opencode.ai/docs/', ['opencode', 'auth', 'login']),
    'gemini': ('Gemini', 'gemini', 'https://geminicli.com/docs/get-started/authentication/', ['gemini']),
    'hermes': ('Hermes', 'hermes', 'https://hermes-agent.nousresearch.com/docs/', ['hermes', 'portal']),
}
DISCLOSURE = ('Only the bounded selected capture text and task instructions are sent to the selected connection/model '
              'and its underlying provider (including routing through OpenRouter or Nous where selected). '
              'Remote inference may cost money. Review the actual destination and account privacy settings before consenting. '
              'Provider retention/training terms and safety/legal retention exceptions apply; no no-retention guarantee. '
              'External CLI clients may retain task/session traces in their app-owned profile. '
              'Only implemented bounded transports can be checked; sign-in or installation alone never enables processing. '
              'No silent model/provider fallback; canonical knowledge stays local; all proposals require human review.')


class Configuration(StrictModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    connection: Literal['chatgpt', 'copilot', 'openrouter', 'opencode', 'gemini', 'hermes']
    model: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$')


def require_human(human):
    if human is not True:
        raise DomainError('approval_required', 403)


def configuration(value):
    try:
        result = Configuration.model_validate(value).model_dump()
        # Reject whole routing/alias segments, not substrings of explicit names.
        import re
        if any(segment.lower() in {'auto', 'default', 'latest'}
               for segment in re.split(r'[/@:]', result['model'])):
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise DomainError('invalid_configuration', 422) from None


class KeychainVault:
    """Only app-owned Generic Password items. No CLI stores or shell argv secrets."""
    def __init__(self, *, security=None):
        if security is None:
            try:
                import Security as security
            except ImportError:
                raise DomainError('credential_store_unavailable', 503) from None
        self.security = security

    def _query(self, name):
        s = self.security
        return {s.kSecClass: s.kSecClassGenericPassword,
                s.kSecAttrService: 'Knowledge Hub Curator', s.kSecAttrAccount: name}

    def get(self, name):
        s = self.security
        try:
            status, value = s.SecItemCopyMatching({**self._query(name), s.kSecReturnData: True,
                                                  s.kSecMatchLimit: s.kSecMatchLimitOne}, None)
            if status == s.errSecItemNotFound:
                return None
            if status != s.errSecSuccess:
                raise ValueError()
            return bytes(value).decode('utf-8')
        except Exception:
            raise DomainError('credential_store_unavailable', 503) from None

    def put(self, name, value):
        s = self.security
        try:
            status, _ = s.SecItemAdd({**self._query(name), s.kSecValueData: value.encode('utf-8')}, None)
            if status == s.errSecDuplicateItem:
                status = s.SecItemUpdate(self._query(name), {s.kSecValueData: value.encode('utf-8')})
            if status != s.errSecSuccess or self.get(name) != value:
                raise ValueError()
        except Exception:
            raise DomainError('credential_store_unavailable', 503) from None


from .connection_profiles import ProfileConnections


class Connections(ProfileConnections):
    def __init__(self, store, *, vault=None, discover=None):
        self.store = store
        self.root = store.path.parent
        self.path = self.root / 'curator-connection.json'
        self.vault = vault  # Keychain is created lazily, never queried on startup.
        self.discover = discover or shutil.which
        self._auth = None
        self._auth_lock = threading.Lock()

    def _vault(self):
        if self.vault is None:
            self.vault = KeychainVault()
        return self.vault

    def start_auth(self, connection, *, human=False, callback_url=None):
        require_human(human)
        if connection not in PRESETS:
            raise DomainError('invalid_configuration', 422)
        _, executable, guide, command = PRESETS[connection]
        if executable:
            from .cli_auth import auth_handoff
            return auth_handoff(self.root, connection, self.discover(executable), guide, command)
        try:
            if not isinstance(callback_url, str) or any(ord(char) < 33 or ord(char) > 126 for char in callback_url):
                raise ValueError()
            parsed = urlparse(callback_url)
            if (parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1'}
                    or not parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or parsed.path not in {'/api/curator/auth/callback', '/curator-auth/callback'}):
                raise ValueError()
        except ValueError:
            raise DomainError('invalid_callback', 422) from None
        with data_lock(self.root):
            current = self._load()
            if (current['connection'] != connection or current['consent'] is not True
                    or not current.get('generation')):
                raise DomainError('configuration_confirmation_required', 403)
            with self._auth_lock:
                state = secrets.token_urlsafe(32)
                verifier = secrets.token_urlsafe(64)
                self._auth = (state, verifier, time.monotonic() + 600, current['generation'])
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        return {'status': 'human_auth_handoff', 'url': 'https://openrouter.ai/auth?' + urlencode({
            'callback_url': callback_url, 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256'})}

    def exchange(self, url, body, headers=None):
        from .connection_transport import json_request
        return json_request(url, body, headers)

    def complete_auth(self, state, code, *, human=False):
        require_human(human)
        # Always take the data-root lock before the in-memory auth lock.
        with data_lock(self.root):
            with self._auth_lock:
                pending = self._auth
                if (not pending or not isinstance(state, str) or not secrets.compare_digest(pending[0], state)
                        or pending[2] <= time.monotonic()
                        or self._load().get('generation') != pending[3]):
                    raise DomainError('invalid_auth_state', 403)
                self._auth = None  # Consume before exchange; never replay an authorization code.
        if not isinstance(code, str) or not 1 <= len(code) <= 4096 or any(ord(c) < 33 for c in code):
            raise DomainError('invalid_auth_code', 422)
        try:
            response = self.exchange('https://openrouter.ai/api/v1/auth/keys', {
                'code': code, 'code_verifier': pending[1], 'code_challenge_method': 'S256'})
            key = response['key']
            with data_lock(self.root):
                if self._load().get('generation') != pending[3]:
                    raise DomainError('invalid_auth_state', 403)
                return self.set_key('openrouter', key, human=True)
        except DomainError:
            raise
        except Exception:
            raise DomainError('authentication_failed', 502) from None

    def set_key(self, connection, key, *, human=False):
        require_human(human)
        if connection != 'openrouter' or not isinstance(key, str) or not 1 <= len(key) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise DomainError('invalid_credential', 422)
        with data_lock(self.root):
            state = self._load()
            if state['connection'] != connection or not state['consent']:
                raise DomainError('configuration_confirmation_required', 403)
            self._vault().put(self.credential_name(), key)
            state.update(status='unchecked', enabled=False, last_error=None, generation=secrets.token_hex(16))
            self._save(state)
            with self._auth_lock:
                self._auth = None
            return self.state()

    def catalog(self):
        from .cli_models import GeminiAdapter
        items = []
        for key, (name, executable, url, _) in PRESETS.items():
            supported = key != 'chatgpt'
            installed = bool(self.discover(executable)) if executable else True
            reason = ('Official CLI sign-in uses an app-owned profile. A human-requested synthetic connection test '
                      'and separate enablement are required; installed does not mean authenticated.')
            if key == 'chatgpt':
                reason = ('Official Codex login is available, but a verified deny-all tool execution contract is '
                          'not established for Codex 0.166.0. Read-only sandbox is not tool denial; inference remains blocked.')
            elif key == 'hermes':
                reason = ('Human sign-in uses hermes portal in an app-owned HERMES_HOME, followed by hermes proxy start. '
                          'Only the Nous subscription pure-inference proxy is used, never the tool-enabled agent API. '
                          'Synthetic test and explicit enablement remain required.')
            elif key == 'openrouter':
                reason = 'App-owned credentials use the OS credential store; synthetic check and explicit enablement required.'
            items.append(dict(id=key, name=name, transport='cli' if executable else 'https',
                capability='bounded_text' if supported else 'tool_denial_unverified',
                availability=('missing_cli' if not installed else 'sign_in_required' if supported else 'unsupported_capability'),
                readiness='not_checked', auth_methods=['official_cli'] if executable else ['pkce', 'api_key'],
                install_url=url, reason=reason,
                supported_models=sorted(GeminiAdapter.MODELS) if key == 'gemini' else None))
        return {'connections': items, 'auth_routes': self.route_catalog(), 'disclosure': DISCLOSURE}

    def _load(self):
        raw = self._raw()
        if raw.get('version') == 2:
            active = raw['active_profile_id']
            value = dict(raw['profiles'][active]) if active else {
                'connection': None, 'model': None, 'enabled': False, 'consent': False,
                'status': 'unconfigured', 'last_error': None}
            if 'staged' in raw: value['staged'] = raw['staged']
            return value
        return raw or {'connection': None, 'model': None, 'enabled': False, 'consent': False,
                       'status': 'unconfigured', 'last_error': None}

    def _save(self, value):
        raw = self._raw()
        if raw.get('version') == 2:
            active = raw['active_profile_id']
            if value.get('profile_id') not in {None, active}:
                raise DomainError('configuration_changed', 409)
            if active:
                raw['profiles'][active] = {**raw['profiles'][active], **value}
            if 'staged' in value: raw['staged'] = value['staged']
            self._write_registry(raw)
        else:
            self._write_registry(value)

    def state(self):
        with data_lock(self.root):
            return self._load()

    def stage(self, value):
        proposed = configuration(value)
        with data_lock(self.root):
            state = self._load()
            state['staged'] = proposed
            self._save(state)
            return self.state()

    def enable(self, enabled, *, human=False):
        require_human(human)
        if type(enabled) is not bool:
            raise DomainError('invalid_configuration', 422)
        with data_lock(self.root):
            state = self._load()
            if enabled and (not state['consent'] or state['status'] != 'checked'
                            or state['connection'] not in {'openrouter', 'copilot', 'opencode', 'hermes', 'gemini'}):
                raise DomainError('diagnostic_required', 409)
            state['enabled'] = enabled
            self._save(state)
            return self.state()

    def confirm(self, value, *, consent, human=False):
        require_human(human)
        proposed = configuration(value)
        if consent is not True:
            raise DomainError('privacy_consent_required', 403)
        with data_lock(self.root):
            status = next(item['availability'] for item in self.catalog()['connections'] if item['id'] == proposed['connection'])
            self._save({**proposed, 'enabled': False, 'consent': True, 'status': status, 'last_error': None,
                        'generation': secrets.token_hex(16)})
            with self._auth_lock:
                self._auth = None
            return self.state()
