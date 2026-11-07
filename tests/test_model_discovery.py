import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from knowledge_hub.core import DomainError


def test_fixed_get_transport_authenticates_and_never_redirects():
    from knowledge_hub.model_discovery import get_json
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            requests.append((self.path, self.headers.get('Authorization')))
            if self.path == '/redirect':
                self.send_response(302); self.send_header('Location', 'https://evil.test'); self.end_headers(); return
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({'data': [{'id': 'synthetic/model'}]}).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}'
        result = get_json(url+'/models', {'Authorization': 'Bearer SYNTHETIC'}, allow_loopback=True)
        assert result['data'][0]['id'] == 'synthetic/model'
        assert requests == [('/models', 'Bearer SYNTHETIC')]
        with pytest.raises(DomainError, match='unsafe_provider_url'): get_json(url+'/models')
        with pytest.raises(DomainError, match='provider_http_error'): get_json(url+'/redirect', allow_loopback=True)
        with pytest.raises(DomainError, match='unsafe_provider_url'): get_json('https://openrouter.ai.evil.test/api/v1/models/user')
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_openrouter_account_models_are_filtered_for_adapter_not_claimed_entitled(tmp_path):
    from knowledge_hub.model_discovery import discover_models
    calls = []
    def transport(url, headers):
        calls.append((url, headers))
        return {'data': [
            {'id': 'vendor/good', 'name': 'Good', 'architecture': {'input_modalities': ['text'], 'output_modalities': ['text']}, 'supported_parameters': ['response_format', 'max_tokens']},
            {'id': 'vendor/no-json', 'supported_parameters': []},
            {'id': 'vendor/image', 'architecture': {'output_modalities': ['image']}, 'supported_parameters': ['response_format', 'max_tokens']} ]}
    result = discover_models('openrouter_api_key', 'SYNTHETIC', tmp_path, transport=transport)
    assert calls == [('https://openrouter.ai/api/v1/models/user', {'Authorization': 'Bearer SYNTHETIC'})]
    assert result['models'] == [{'id': 'vendor/good', 'name': 'Good'}]
    assert result['availability'] == 'account_filtered_not_inference_verified'
    with pytest.raises(DomainError, match='sign_in_required'):
        discover_models('openrouter_api_key', None, tmp_path, transport=transport)
    with pytest.raises(DomainError, match='model_discovery_unsupported'):
        discover_models('hermes_agent_cli', None, tmp_path, transport=transport)
