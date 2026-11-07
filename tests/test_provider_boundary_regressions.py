"""Synthetic regressions for explicit-model and privacy enforcement."""
import json
import pytest
from knowledge_hub.core import DomainError
from knowledge_hub.connection_transport import OpenRouterAdapter
from knowledge_hub.cli_connections import CLIAdapter

DRAFT = {'summary': 'Synthetic', 'operations': [{'title': 'Sky', 'body': 'Sky is blue', 'kind': 'fact', 'quote': 'Sky is blue'}]}
PACKET = {'text': 'Sky is blue', 'intent': 'Add knowledge'}


def test_opencode_openrouter_route_is_blocked_before_process_launch(tmp_path, monkeypatch):
    adapter = CLIAdapter.__new__(CLIAdapter)
    adapter.connection = 'opencode'
    adapter.root = tmp_path
    adapter.cancel = None
    adapter.executable = '/synthetic/opencode'
    adapter.fixture_url = None
    adapter.timeout = 1
    def unexpected(*args, **kwargs):
        pytest.fail('blocked route started a CLI process')
    monkeypatch.setattr('knowledge_hub.cli_connections._run', unexpected)
    with pytest.raises(DomainError, match='privacy_route_unsupported'):
        adapter.complete('openrouter/openai/gpt-5.4', None, PACKET, consented=True)


@pytest.mark.parametrize('model,finish', [('different/model', 'stop'), ('synthetic/model', 'provider_unknown'), ('synthetic/model', None), (None, 'stop')])
def test_openrouter_requires_selected_model_and_completed_response(model, finish):
    result = {'model': model, 'choices': [{'message': {'content': json.dumps(DRAFT)}, 'finish_reason': finish}]}
    adapter = OpenRouterAdapter(transport=lambda *args: result)
    with pytest.raises(DomainError, match='invalid_provider_response'):
        adapter.complete('synthetic/model', 'SYNTHETIC', PACKET)
