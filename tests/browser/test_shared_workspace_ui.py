"""Approved shared-workspace UI, real loopback handlers and synthetic stores."""
from test_reader import page, server
from playwright.sync_api import expect
import pytest


def open_workspace(page, server):
    page.goto(server + '/#token=synthetic-browser-human')
    expect(page.locator('#content h1')).to_have_text('Your knowledge starts here')


def test_fresh_install_starts_with_capture_without_project_setup(page, server):
    open_workspace(page, server)
    expect(page.get_by_label('Capture', exact=True)).to_be_visible()
    expect(page.get_by_label('Intention', exact=True)).to_have_value('add_knowledge')
    expect(page.get_by_role('button', name='New project', exact=True)).to_have_count(0)
    expect(page.get_by_label('Project name', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Activity', exact=False)).to_be_visible()
    expect(page.get_by_role('button', name='Settings', exact=True)).to_be_visible()
    expect(page.locator('.book-entry')).to_have_count(0)
    page.get_by_label('Capture', exact=True).fill('Synthetic first shared knowledge')
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Review capture')
    expect(page.get_by_role('heading', name='Awaiting agent', exact=True)).to_be_visible()
    captures = page.request.get(server + '/api/captures').json()['captures']
    assert len(captures) == 1
    saved = page.request.get(server + '/api/captures/' + captures[0]['id']).json()
    assert saved['text'] == 'Synthetic first shared knowledge'
    assert saved['intent'] == 'Add knowledge'
    assert page.request.get(server + '/api/warehouse').json()['items'] == []


def test_explicit_request_draft_and_files_survive_global_navigation(page, server):
    open_workspace(page, server)
    page.get_by_role('button', name='Draft options', exact=True).click()
    page.get_by_label('Intention', exact=True).select_option('request')
    page.keyboard.press('Escape')
    page.get_by_label('Capture', exact=True).fill('Explain the synthetic subject briefly')
    page.get_by_label('Attach files', exact=True).set_input_files(
        {'name': 'synthetic-request.txt', 'mimeType': 'text/plain', 'buffer': b'Synthetic request context'})
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_role('button', name='Back to Library', exact=True).click()
    expect(page.get_by_label('Intention', exact=True)).to_have_value('request')
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Explain the synthetic subject briefly')
    expect(page.get_by_text('synthetic-request.txt', exact=True)).to_be_visible()
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Review capture')
    captures = page.request.get(server + '/api/captures').json()['captures']
    saved = page.request.get(server + '/api/captures/' + captures[0]['id']).json()
    assert saved['intent'] == 'Request something'
    assert saved['files'][0]['name'] == 'synthetic-request.txt'
    assert page.request.get(server + '/api/library/books').json()['books'] == []


def test_knowledge_without_books_is_not_a_fresh_install_or_placeholder_shelf(page, server):
    from test_reader import seed
    open_workspace(page, server)
    seed(page, server, 'Synthetic accepted finding', 'Knowledge does not require a book.')
    page.reload()
    expect(page.locator('#content h1')).to_have_text('Library')
    expect(page.get_by_text('Your knowledge is saved. No reading subjects have been published yet.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Request a reading subject', exact=True)).to_be_visible()
    expect(page.locator('.book-entry')).to_have_count(0)
    expect(page.get_by_text('Make room for your first book', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Request a reading subject', exact=True).click()
    expect(page.get_by_label('Intention', exact=True)).to_have_value('request')
    expect(page.get_by_label('Capture', exact=True)).to_be_focused()


def test_populated_library_uses_titles_and_descriptions_not_statistics(page, server):
    from test_first_release_ui import seed_book
    open_workspace(page, server)
    seed_book(page, server)
    page.reload()
    expect(page.locator('#content h1')).to_have_text('Library')
    entry = page.locator('.book-entry')
    expect(entry.get_by_role('heading', name='Synthetic reader handbook', exact=True)).to_be_visible()
    expect(entry.get_by_text('Read with registered support', exact=True)).to_be_visible()
    expect(entry).not_to_contain_text('1 page')
    expect(entry.locator('img')).to_have_count(0)
    entry.get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Synthetic reader handbook')
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('A synthetic first page')
    expect(page.get_by_role('button', name='Inspect Synthetic shared basis', exact=True)).to_be_visible()


def test_activity_keeps_saved_work_reachable_and_shows_only_real_processing(page, server):
    from knowledge_hub.curator import Curator
    from knowledge_hub.shared import SharedWarehouse
    open_workspace(page, server)
    page.get_by_label('Capture', exact=True).fill('Synthetic queued material')
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Review capture')
    page.get_by_role('button', name='Activity', exact=False).click()
    expect(page.locator('#content h1')).to_have_text('Activity')
    expect(page.get_by_text('Saved locally · waiting for an agent', exact=True)).to_be_visible()
    page.locator('#content').get_by_role('button', name='Review saved capture', exact=False).click()
    expect(page.get_by_text('Synthetic queued material', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='In progress', exact=True)).to_have_count(0)
    assert page.request.post(server + '/api/agent/access', data={'enabled': True}).ok
    capture = page.request.get(server + '/api/captures').json()['captures'][0]
    scope = SharedWarehouse(server.store).scope()
    Curator(server.store).claim(scope, capture['id'], 'Synthetic browser agent', capture['snapshot_sha256'], 0)
    page.get_by_role('button', name='Refresh agent result', exact=True).click()
    expect(page.get_by_role('heading', name='In progress', exact=True)).to_be_visible()
    page.get_by_role('button', name='Activity', exact=False).click()
    expect(page.get_by_text('In progress · claimed by an agent', exact=True)).to_be_visible()


def test_settings_offers_six_connections_one_model_and_human_confirmation(page, server):
    server.connections.discover = lambda executable: None
    open_workspace(page, server)
    page.get_by_role('button', name='Settings', exact=True).click()
    connection = page.get_by_label('Connection', exact=True)
    expect(connection.locator('option')).to_have_count(7)
    for name in ['ChatGPT', 'GitHub Copilot', 'OpenRouter', 'OpenCode', 'Gemini', 'Hermes']:
        expect(connection.locator('option').get_by_text(name, exact=True)).to_have_count(1)
    connection.select_option('chatgpt')
    expect(page.get_by_text('CLI not installed', exact=True)).to_be_visible()
    expect(page.get_by_label('Model', exact=True)).to_have_count(1)
    expect(page.get_by_label('Ingestion model', exact=True)).to_have_count(0)
    page.get_by_label('Model', exact=True).fill('synthetic-model')
    save = page.get_by_role('button', name='Confirm connection and model', exact=True)
    expect(save).to_be_disabled()
    page.get_by_label('I approve this connection, model and disclosure scope', exact=True).check()
    save.click()
    expect(page.get_by_text('Saved. Processing remains disabled.', exact=True)).to_be_visible()
    actual = page.request.get(server + '/api/curator').json()
    assert actual['connection'] == 'chatgpt'
    assert actual['model'] == 'synthetic-model'
    assert actual['enabled'] is False
    assert actual['status'] == 'missing_cli'
    expect(page.get_by_role('button', name='Enable processing', exact=True)).to_be_disabled()
    expect(page.get_by_role('heading', name='External agent', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Check for Updates', exact=True)).to_be_visible()


def test_openrouter_auth_is_human_handoff_and_key_never_reappears(page, server):
    class SyntheticVault:
        value = None
        def put(self, name, value): self.value = value
        def get(self, name): return self.value
    vault = SyntheticVault()
    server.connections.vault = vault
    open_workspace(page, server)
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_label('Connection', exact=True).select_option('openrouter')
    page.get_by_label('Model', exact=True).fill('synthetic/model')
    page.get_by_label('I approve this connection, model and disclosure scope', exact=True).check()
    page.get_by_role('button', name='Confirm connection and model', exact=True).click()
    expect(page.get_by_text('Saved. Processing remains disabled.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Sign in with OpenRouter', exact=True).click()
    link = page.get_by_role('link', name='Continue to OpenRouter', exact=True)
    expect(link).to_have_attribute('target', '_blank')
    href = link.get_attribute('href')
    assert href.startswith('https://openrouter.ai/auth?')
    assert len(page.context.pages) == 1
    page.get_by_label('OpenRouter API key', exact=True).fill('synthetic-not-a-real-key')
    page.get_by_role('button', name='Save key securely', exact=True).click()
    expect(page.get_by_label('OpenRouter API key', exact=True)).to_have_value('')
    expect(page.get_by_text('Credential saved in the OS credential store.', exact=True)).to_be_visible()
    assert vault.value == 'synthetic-not-a-real-key'
    assert 'synthetic-not-a-real-key' not in page.request.get(server + '/api/curator').text()
    assert page.request.get(server + '/api/curator').json()['enabled'] is False


def test_fresh_desktop_capture_keeps_save_action_in_first_viewport(page, server):
    page.set_viewport_size({'width': 1440, 'height': 900})
    open_workspace(page, server)
    expect(page.get_by_role('button', name='Send', exact=True)).to_be_in_viewport()


def test_late_capture_save_does_not_erase_a_newer_shared_draft(page, server):
    open_workspace(page, server)
    page.get_by_label('Capture', exact=True).fill('Synthetic submitted snapshot')
    page.evaluate("""() => {
      const original = window.fetch;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (String(args[0]) === '/api/captures' && args[1]?.method === 'POST') {
          document.documentElement.dataset.captureDelayed = 'true';
          await new Promise(resolve => { window.releaseCapture = resolve; });
        }
        return response;
      };
    }""")
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('html')).to_have_attribute('data-capture-delayed', 'true')
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_label('Capture', exact=True).fill('Synthetic newer unfinished draft')
    page.evaluate('window.releaseCapture()')
    page.wait_for_timeout(150)
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Synthetic newer unfinished draft')
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Synthetic newer unfinished draft')
    captures = page.request.get(server + '/api/captures').json()['captures']
    assert len(captures) == 1
    assert page.request.get(server + '/api/captures/' + captures[0]['id']).json()['text'] == 'Synthetic submitted snapshot'


def test_auth_handoff_rejects_unsafe_external_url(page, server):
    server.connections.start_auth = lambda *args, **kwargs: {'status': 'human_auth_handoff', 'url': 'javascript:alert(1)'}
    open_workspace(page, server)
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_label('Connection', exact=True).select_option('openrouter')
    page.get_by_role('button', name='Sign in with OpenRouter', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('unsafe sign-in link')
    expect(page.locator('a[href^="javascript:"]')).to_have_count(0)


def test_synthetic_check_enable_and_one_item_run_never_accepts_knowledge(page, server):
    class SyntheticVault:
        def get(self, name): return 'synthetic-runtime-key'
    server.connections.vault = SyntheticVault()
    calls = []
    def synthetic_adapter(model, key, packet, cancelled):
        calls.append(packet['text'])
        return {'summary': 'Synthetic pending result', 'operations': [
            {'title': 'Synthetic app-managed finding', 'body': packet['text'], 'kind': 'finding', 'quote': packet['text']}]}
    server.curator_runtime.execute = synthetic_adapter
    open_workspace(page, server)
    assert page.request.post(server + '/api/curator/config', data={
        'configuration': {'connection': 'openrouter', 'model': 'synthetic/model'}, 'confirm': True, 'consent': True}).ok
    assert page.request.post(server + '/api/agent/access', data={'enabled': True}).ok
    assert page.request.post(server + '/api/captures', data={'text': 'Synthetic queued task', 'intent': 'add_knowledge'}).ok
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_role('button', name='Run synthetic connection check', exact=True).click()
    expect(page.get_by_text('Connection status: Check passed', exact=True)).to_be_visible()
    expect(page.get_by_text('Sign-in required', exact=True)).to_have_count(0)
    assert calls == ['Synthetic sky is blue']
    assert page.request.get(server + '/api/changes').json()['changes'] == []
    page.get_by_role('button', name='Enable processing', exact=True).click()
    expect(page.get_by_text('Processing: enabled', exact=True)).to_be_visible()
    page.get_by_role('button', name='Process next capture', exact=True).click()
    expect(page.get_by_text('Proposal ready for human review.', exact=True)).to_be_visible()
    assert calls == ['Synthetic sky is blue', 'Synthetic queued task']
    changes = page.request.get(server + '/api/changes').json()['changes']
    assert len(changes) == 1 and changes[0]['status'] == 'pending'
    assert page.request.get(server + '/api/warehouse').json()['items'] == []
    page.get_by_role('button', name='Disable processing', exact=True).click()
    expect(page.get_by_text('Processing: disabled', exact=True)).to_be_visible()


def test_request_capture_is_not_silently_run_as_factual_ingestion(page, server):
    class SyntheticVault:
        def get(self, name): return 'synthetic-only-key'
    server.connections.vault = SyntheticVault()
    calls = []
    def synthetic_adapter(model, key, packet, cancelled):
        calls.append(packet['text'])
        return {'summary': 'Synthetic check', 'operations': [
            {'title': 'Synthetic check fact', 'body': packet['text'], 'kind': 'fact', 'quote': packet['text']}]}
    server.curator_runtime.execute = synthetic_adapter
    open_workspace(page, server)
    page.get_by_role('button', name='Draft options', exact=True).click()
    page.get_by_label('Intention', exact=True).select_option('request')
    page.keyboard.press('Escape')
    page.get_by_label('Capture', exact=True).fill('Explain the synthetic subject')
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Review capture')
    assert page.request.post(server + '/api/curator/config', data={
        'configuration': {'connection': 'openrouter', 'model': 'synthetic/model'}, 'confirm': True, 'consent': True}).ok
    assert page.request.post(server + '/api/agent/access', data={'enabled': True}).ok
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_role('button', name='Run synthetic connection check', exact=True).click()
    expect(page.get_by_text('Connection status: Check passed', exact=True)).to_be_visible()
    page.get_by_role('button', name='Enable processing', exact=True).click()
    expect(page.get_by_text('Processing: enabled', exact=True)).to_be_visible()
    page.get_by_role('button', name='Process next capture', exact=True).click()
    expect(page.get_by_text('This request needs your external agent. It remains saved locally.', exact=True)).to_be_visible()
    assert calls == ['Synthetic sky is blue']
    assert page.request.get(server + '/api/changes').json()['changes'] == []


def test_failed_connection_check_reads_back_blocked_state_and_preserves_model(page, server):
    from knowledge_hub.core import DomainError
    class SyntheticVault:
        def get(self, name): return 'synthetic-only-key'
    server.connections.vault = SyntheticVault()
    def failed_adapter(*args): raise DomainError('provider_http_error', 502)
    server.curator_runtime.execute = failed_adapter
    open_workspace(page, server)
    assert page.request.post(server + '/api/curator/config', data={
        'configuration': {'connection': 'openrouter', 'model': 'synthetic/model'}, 'confirm': True, 'consent': True}).ok
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_role('button', name='Run synthetic connection check', exact=True).click()
    expect(page.get_by_text('Connection status: Check failed', exact=True)).to_be_visible()
    expect(page.get_by_label('Model', exact=True)).to_have_value('synthetic/model')
    expect(page.get_by_role('button', name='Enable processing', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='Run synthetic connection check', exact=True)).to_be_enabled()
    expect(page.get_by_role('alert')).to_contain_text('provider rejected')
    assert page.request.get(server + '/api/curator').json()['enabled'] is False


@pytest.mark.parametrize('width', [320, 390, 1440])
def test_fresh_composer_and_global_settings_fit_without_an_empty_index(page, server, width):
    page.set_viewport_size({'width': width, 'height': 900})
    open_workspace(page, server)
    expect(page.locator('.index')).not_to_be_visible()
    expect(page.get_by_label('Capture', exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_label('Connection', exact=True).select_option('openrouter')
    expect(page.get_by_label('OpenRouter API key', exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Back to Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_be_visible()


def test_capture_network_failure_preserves_text_and_attachments_for_retry(page, server):
    """Supplemental error recovery coverage over the real capture handler."""
    open_workspace(page, server)
    page.get_by_label('Capture', exact=True).fill('Synthetic unsent material')
    page.get_by_label('Attach files', exact=True).set_input_files(
        {'name': 'synthetic-retry.txt', 'mimeType': 'text/plain', 'buffer': b'Synthetic retry attachment'})
    page.route('**/api/captures', lambda route: route.abort('failed'))
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('could not be reached')
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Synthetic unsent material')
    expect(page.get_by_text('synthetic-retry.txt', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Send', exact=True)).to_be_enabled()
    page.unroute('**/api/captures')
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Review capture')
    expect(page.get_by_text('Synthetic retry attachment', exact=True)).to_be_visible()


@pytest.mark.parametrize('source', ['library', 'settings'])
def test_late_library_or_settings_read_does_not_replace_current_input(page, server, source):
    """Supplemental real-response navigation race characterization."""
    open_workspace(page, server)
    delayed = '/api/library/books' if source == 'library' else '/api/curator'
    page.evaluate("""delayed => {
      const original = window.fetch;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (String(args[0]) === delayed) {
          document.documentElement.dataset.readDelayed = 'true';
          await new Promise(resolve => { window.releaseRead = resolve; });
        }
        return response;
      };
    }""", delayed)
    page.get_by_role('button', name='Library' if source == 'library' else 'Settings', exact=True).click()
    expect(page.locator('html')).to_have_attribute('data-read-delayed', 'true')
    if source == 'library':
        page.get_by_role('button', name='Settings', exact=True).click()
        field = page.get_by_label('Model', exact=True)
    else:
        page.get_by_role('button', name='Library', exact=True).click()
        field = page.get_by_label('Capture', exact=True)
    field.fill('Synthetic input after navigation')
    page.evaluate('window.releaseRead()')
    page.wait_for_timeout(150)
    expect(field).to_have_value('Synthetic input after navigation')


def test_rendered_shared_states_synthetic_evidence(page, server, tmp_path):
    """Supplemental render verification, not real provider or quality evidence."""
    from pathlib import Path
    import json
    from test_reader import seed
    from test_first_release_ui import seed_book
    import os
    output = Path(os.environ.get('KH_SHARED_UI_ARTIFACTS', str(tmp_path / 'shared-workspace-evidence')))
    output.mkdir(parents=True, exist_ok=True)
    artifacts, errors, requests = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append(request.url))
    def shot(name, width):
        page.set_viewport_size({'width': width, 'height': 800})
        page.evaluate('document.activeElement.blur(); window.scrollTo(0, 0)')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(output / (name + '.png')), full_page=False)
        artifacts.append({'path': str(output / (name + '.png')), 'synthetic': True, 'width': width})
    open_workspace(page, server)
    shot('synthetic-empty-desktop', 1440)
    shot('synthetic-empty-390', 390)
    shot('synthetic-empty-320', 320)
    seed(page, server, 'Synthetic basis for a subject', 'Accepted knowledge can exist without a reading subject.')
    page.reload()
    expect(page.locator('#content h1')).to_have_text('Library')
    shot('synthetic-knowledge-without-books', 1440)
    seed_book(page, server)
    page.reload()
    expect(page.locator('.book-entry')).to_have_count(1)
    shot('synthetic-library-desktop', 1440)
    shot('synthetic-library-390', 390)
    page.set_viewport_size({'width': 1440, 'height': 960})
    page.get_by_role('button', name='Settings', exact=True).click()
    expect(page.get_by_label('Connection', exact=True)).to_be_visible()
    shot('synthetic-settings-desktop', 1440)
    shot('synthetic-settings-390', 390)
    page.set_viewport_size({'width': 1440, 'height': 960})
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_label('Capture', exact=True).fill('Synthetic capture awaiting human review')
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Review capture')
    page.get_by_role('button', name='Activity', exact=False).click()
    expect(page.locator('#content h1')).to_have_text('Activity')
    shot('synthetic-activity-desktop', 1440)
    assert not errors
    assert all(url.startswith(server) or url.startswith('data:image/') for url in requests)
    (output / 'manifest.json').write_text(json.dumps(artifacts, indent=2))

