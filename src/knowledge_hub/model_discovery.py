"""Human-requested model catalogues. Never infer entitlement from a listing."""
import http.client
import ssl
import time
from urllib.parse import urlparse
from .core import DomainError
from .intake_http import strict_json

OPENROUTER_MODELS = 'https://openrouter.ai/api/v1/models/user'
MAX_CATALOG = 4 * 1024 * 1024


def get_json(url, headers=None, *, timeout=15, allow_loopback=False):
    parsed = urlparse(url)
    fixture = (allow_loopback is True and parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
               and parsed.port and not parsed.username and not parsed.password and not parsed.fragment)
    if url != OPENROUTER_MODELS and not fixture: raise DomainError('unsafe_provider_url', 422)
    client = (http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=timeout, context=ssl.create_default_context())
              if parsed.scheme == 'https' else http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout))
    deadline = time.monotonic() + timeout
    try:
        client.request('GET', parsed.path + ('?' + parsed.query if parsed.query else ''), headers={
            'Accept': 'application/json', 'Accept-Encoding': 'identity', **(headers or {})})
        response = client.getresponse()
        if response.status in {401, 403}: raise DomainError('sign_in_required', 403)
        if response.status != 200: raise DomainError('provider_http_error', 502)
        content = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError()
            if client.sock: client.sock.settimeout(remaining)
            chunk = response.read1(min(65536, MAX_CATALOG + 1 - len(content)))
            content.extend(chunk)
            if len(content) > MAX_CATALOG: raise DomainError('provider_response_size_limit', 502)
            if not chunk: break
        value = strict_json(content.decode('utf-8'))
        if not isinstance(value, dict): raise ValueError()
        return value
    except DomainError: raise
    except (OSError, TimeoutError, http.client.HTTPException):
        raise DomainError('provider_unavailable', 502) from None
    except (ValueError, TypeError, RecursionError):
        raise DomainError('invalid_provider_response', 502) from None
    finally: client.close()


def discover_models(route, key, root, *, transport=None):
    if route not in {'openrouter_api_key', 'openrouter_oauth'}:
        # Other clients must expose an authenticated machine-readable API before
        # they can be offered here. A bundled/static list is not account discovery.
        raise DomainError('model_discovery_unsupported', 409)
    if not key: raise DomainError('sign_in_required', 403)
    response = (transport or get_json)(OPENROUTER_MODELS, {'Authorization': 'Bearer ' + key})
    try:
        data = response['data']
        if not isinstance(data, list) or len(data) > 5000: raise ValueError()
        models = []
        for item in data:
            architecture = item.get('architecture', {})
            if ('text' not in architecture.get('input_modalities', ['text'])
                    or 'text' not in architecture.get('output_modalities', ['text'])): continue
            if item.get('endpoints') is not None and '/api/v1/chat/completions' not in item['endpoints']: continue
            if not {'response_format', 'max_tokens'} <= set(item.get('supported_parameters', [])): continue
            models.append({'id': item['id'], 'name': item.get('name', item['id'])})
        # Omitting offset/limit requests the full catalogue. Never follow links
        # returned by a provider (which might otherwise become an SSRF redirect).
        if response.get('links', {}).get('next'):
            raise DomainError('incomplete_model_catalog', 502)
        return {'models': models, 'source': OPENROUTER_MODELS,
                'availability': 'account_filtered_not_inference_verified'}
    except DomainError: raise
    except (ValueError, KeyError, TypeError, AttributeError):
        raise DomainError('invalid_provider_response', 502) from None
