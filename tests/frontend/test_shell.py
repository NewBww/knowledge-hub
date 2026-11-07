"""Shipping shell contract; no knowledge is bundled in the assets."""
from pathlib import Path
from html.parser import HTMLParser

WEB = Path(__file__).parents[2] / 'src/knowledge_hub/web'

class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

def test_accessible_local_shell():
    assert (WEB / 'index.html').exists(), 'Reader shell is missing'
    elements = Elements((WEB / 'index.html').read_text())
    assert any(tag == 'main' for tag, _ in elements.tags)
    assert any(attrs.get('role') == 'status' for _, attrs in elements.tags)
    assert any(attrs.get('src') == '/assets/app.js' for _, attrs in elements.tags)
    assert any(attrs.get('href') == '/assets/styles.css' for _, attrs in elements.tags)
    assert not any(attrs.get('src', '').startswith('http') for _, attrs in elements.tags)


def test_shipping_ui_has_no_internal_model_or_provider_surface():
    script = (WEB / 'app.js').read_text()
    for forbidden in ['/curator/settings', '/curate', 'api_key_env', 'profile_sha256', 'Process this snapshot']:
        assert forbidden not in script

