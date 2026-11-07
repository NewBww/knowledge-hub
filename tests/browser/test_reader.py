"""Real Chrome + loopback API, with an isolated synthetic workspace."""
import socket
import threading
import time

import pytest
import uvicorn
from playwright.sync_api import sync_playwright, expect
from knowledge_hub.http import create_app

@pytest.fixture
def server(tmp_path):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    app = create_app(tmp_path, human_token='synthetic-browser-human', agent_token='synthetic-browser-agent')
    srv = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=srv.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(.02)
    assert srv.started
    class LocalURL(str):
        pass
    address = LocalURL(f'http://127.0.0.1:{port}')
    address.store = app.state.store
    address.updater = app.state.updater
    address.connections = app.state.connections
    address.curator_runtime = app.state.curator_runtime
    yield address
    srv.should_exit = True
    thread.join(timeout=5)

@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', args=['--window-size=1600,1200'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_default_timeout(5000)
        yield page
        browser.close()

def login(page, server):
    page.goto(server + '/#token=synthetic-browser-human')
    expect(page.get_by_role('heading', name='Your knowledge starts here')).to_be_visible()
    assert '#token' not in page.url


def test_shared_workspace_resumes_cookie_without_project_setup(page, server):
    login(page, server)
    expect(page.get_by_label('Capture', exact=True)).to_be_visible()
    page.reload()
    expect(page.get_by_label('Capture', exact=True)).to_be_visible()
    page.get_by_role('button', name='Warehouse', exact=True).click()
    expect(page.get_by_role('heading', name='Warehouse', exact=True)).to_be_visible()


def create_project(page, server):
    """Legacy helper name; the public workflow has no project creation."""
    login(page, server)
    page.get_by_role('button', name='Warehouse', exact=True).click()


def workspace(page, server):
    from knowledge_hub.shared import SharedWarehouse
    return {**page.request.get(server + '/api/workspace').json(),
            'id': SharedWarehouse(server.store).scope()}


def test_first_topic_requires_explicit_review(page, server):
    create_project(page, server)
    page.get_by_role('button', name='Advanced: add fact', exact=True).click()
    page.get_by_label('Title', exact=True).fill('Synthetic source topic')
    page.get_by_label('Body', exact=True).fill('A synthetic fact for browser verification.')
    page.get_by_role('button', name='Preview proposal', exact=True).click()
    expect(page.get_by_role('heading', name='Review proposed change')).to_be_visible()
    expect(page.get_by_text('A synthetic fact for browser verification.', exact=True)).to_be_visible()
    assert workspace(page, server)['revision'] == 0
    page.get_by_role('button', name='Approve change', exact=True).click()
    expect(page.get_by_role('heading', name='Synthetic source topic', exact=True)).to_be_visible()
    assert workspace(page, server)['revision'] == 1
    expect(page.get_by_text('Current', exact=True)).to_be_visible()


def seed(page, server, title, body, depends_on=None, evidence=None, kind='fact'):
    project = workspace(page, server)
    import uuid
    response = page.request.post(f"{server}/api/changes", data={
        'base_revision': project['revision'], 'idempotency_key': str(uuid.uuid4()), 'summary': 'Synthetic test fixture',
        'operations': [{'op': 'upsert', 'title': title, 'body': body, 'kind': kind,
                        'depends_on': depends_on or [], 'evidence': evidence or []}]})
    assert response.ok, response.text()
    change = response.json()
    response = page.request.post(f"{server}/api/changes/{change['id']}/approve")
    assert response.ok, response.text()
    items = page.request.get(f"{server}/api/warehouse").json()['items']
    return next(item for item in items if item['title'] == title)


def test_read_search_and_inert_content(page, server):
    create_project(page, server)
    seed(page, server, 'Synthetic <img src=x onerror=alert(1)>', '<script>alert(1)</script> Plain body.',
         evidence=[{'kind': 'document', 'locator': 'https://example.com/synthetic', 'label': 'Synthetic reference'},
                   {'kind': 'document', 'locator': 'javascript:alert(1)', 'label': 'Unsafe locator'}])
    seed(page, server, 'Other synthetic topic', 'Other body.')
    page.reload()
    expect(page.locator('#content h1')).to_contain_text('Library')
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='Synthetic <img src=x onerror=alert(1)>', exact=False).click()
    expect(page.get_by_role('heading', name='Synthetic <img src=x onerror=alert(1)>')).to_be_visible()
    expect(page.get_by_text('<script>alert(1)</script> Plain body.', exact=True)).to_be_visible()
    expect(page.get_by_role('link', name='Synthetic reference')).to_have_attribute('href', 'https://example.com/synthetic')
    assert page.locator('#content img, #content script, a[href^="javascript:"]').count() == 0
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='Search Warehouse', exact=True).click()
    page.get_by_role('searchbox').fill('zzzz-no-result')
    expect(page.get_by_text('No topics match your search.', exact=True)).to_be_visible()
    page.get_by_role('searchbox').fill('Other')
    expect(page.get_by_role('button', name='Other synthetic topic', exact=False)).to_be_visible()
    assert page.get_by_role('button', name='Synthetic <img', exact=False).count() == 0
    page.keyboard.press('Meta+k')
    expect(page.get_by_role('searchbox')).to_be_focused()


def test_edit_previews_dependency_impact_and_attention(page, server):
    create_project(page, server)
    source = seed(page, server, 'Synthetic basis', 'Original basis.')
    seed(page, server, 'Synthetic dependent', 'Depends on the basis.', depends_on=[source['id']])
    page.reload()
    expect(page.locator('#content h1')).to_contain_text('Library')
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='Synthetic basis', exact=False).click()
    page.get_by_role('button', name='Propose a change', exact=True).click()
    page.get_by_label('Body', exact=True).fill('Corrected basis.')
    page.get_by_label('Source label', exact=True).fill('Synthetic document')
    page.get_by_label('Source locator', exact=True).fill('https://example.com/basis')
    page.get_by_label('Evidence kind', exact=True).select_option('document')
    page.get_by_role('button', name='Preview proposal', exact=True).click()
    expect(page.get_by_text('Original basis.', exact=True)).to_be_visible()
    expect(page.get_by_text('Corrected basis.', exact=True)).to_be_visible()
    expect(page.get_by_text('Synthetic dependent — needs review', exact=True)).to_be_visible()
    page.get_by_role('button', name='Approve change', exact=True).click()
    page.get_by_role('button', name='Needs attention', exact=True).click()
    page.get_by_role('button', name='Synthetic dependent', exact=False).click()
    expect(page.get_by_text('Needs review', exact=True)).to_be_visible()
    assert page.get_by_role('button', name='Synthetic basis', exact=False).count() == 0


def test_pending_review_reject_and_stale_error(page, server):
    create_project(page, server)
    page.get_by_role('button', name='Advanced: add fact', exact=True).click()
    page.get_by_label('Title', exact=True).fill('Synthetic pending topic')
    page.get_by_label('Body', exact=True).fill('Pending content.')
    page.get_by_role('button', name='Preview proposal', exact=True).click()
    expect(page.get_by_role('heading', name='Review proposed change')).to_be_visible()
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='Activity', exact=False).click()
    expect(page.get_by_role('heading', name='Activity', exact=True)).to_be_visible()
    page.get_by_role('button', name='Synthetic pending topic', exact=False).click()
    seed(page, server, 'Concurrent synthetic topic', 'Changed revision.')
    page.get_by_role('button', name='Approve change', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('workspace changed')
    expect(page.get_by_text('Pending content.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Reject change', exact=True).click()
    page.get_by_role('button', name='Activity', exact=False).click()
    expect(page.get_by_text('No pending changes.', exact=True)).to_be_visible()
    project = workspace(page, server)
    assert project['revision'] == 1
    assert project['review_count'] == 0


def test_lexicon_layout_narrow_navigation_and_long_content(page, server):
    create_project(page, server)
    title = 'Synthetic long title ' + 'unbroken' * 24
    seed(page, server, title, 'Synthetic body.\n\n' + 'Longword' * 70)
    page.reload()
    expect(page.locator('#content h1')).to_contain_text('Library')
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name=title, exact=False).click()
    expect(page.locator('#content h1')).to_have_text(title)
    expect(page.locator('.rail')).to_have_count(0)
    expect(page.locator('.index')).not_to_be_visible()
    assert page.locator('.reader h1').evaluate("el => getComputedStyle(el).fontFamily").startswith('Georgia')
    article = page.locator('#content .prose').bounding_box()
    page.get_by_role('button', name='Propose a change', exact=True).focus()
    assert page.locator('#content .prose').bounding_box() == article
    page.set_viewport_size({'width': 390, 'height': 850})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    expect(page.get_by_role('button', name='Warehouse', exact=True)).to_be_visible()
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='Search Warehouse', exact=True).click()
    expect(page.get_by_role('searchbox')).to_be_visible()
    page.get_by_role('button', name=title, exact=False).click()
    expect(page.locator('#content h1')).to_have_text(title)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Warehouse', exact=True).click()
    expect(page.get_by_role('button', name='Search Warehouse', exact=True)).to_be_visible()
    page.keyboard.press('Meta+k')
    expect(page.get_by_role('searchbox')).to_be_visible()
    expect(page.get_by_role('searchbox')).to_be_focused()


def test_proposal_preview_exposes_kind_sources_and_dependencies(page, server):
    create_project(page, server)
    seed(page, server, 'Synthetic prerequisite', 'A registered prerequisite.')
    page.reload()
    expect(page.locator('#content h1')).to_contain_text('Library')
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='Advanced: add fact', exact=True).click()
    page.get_by_label('Title', exact=True).fill('Synthetic question')
    page.get_by_label('Kind', exact=True).select_option('question')
    page.get_by_label('Body', exact=True).fill('What remains unknown?')
    page.get_by_label('Source label', exact=True).fill('Synthetic source document')
    page.get_by_label('Source locator', exact=True).fill('local/synthetic.txt')
    page.get_by_label('Evidence kind', exact=True).select_option('document')
    page.get_by_label('Synthetic prerequisite', exact=True).check()
    page.get_by_role('button', name='Preview proposal', exact=True).click()
    expect(page.get_by_text('Kind: question', exact=True)).to_be_visible()
    expect(page.get_by_text('Synthetic source document — local/synthetic.txt (document)', exact=True)).to_be_visible()
    expect(page.get_by_text('Depends on: Synthetic prerequisite', exact=True)).to_be_visible()
    page.get_by_role('button', name='Approve change', exact=True).click()
    expect(page.get_by_text('Unresolved', exact=True)).to_be_visible()
    page.get_by_role('button', name='Needs attention', exact=True).click()
    expect(page.get_by_role('button', name='Synthetic question', exact=False)).to_be_visible()


def test_project_opens_reading_and_attention_search_stays_filtered(page, server):
    create_project(page, server)
    seed(page, server, 'Synthetic accepted', 'Accepted body.')
    seed(page, server, 'Synthetic unknown', 'An open question.', kind='question')
    page.reload()
    expect(page.locator('#content h1')).to_contain_text('Library')
    page.get_by_role('button', name='Warehouse', exact=True).click()
    expect(page.get_by_role('heading', name='Warehouse', exact=True)).to_be_visible()
    page.get_by_role('button', name='Needs attention', exact=True).click()
    page.get_by_role('dialog').get_by_role('searchbox').fill('Synthetic')
    dialog = page.get_by_role('dialog', name='Needs attention', exact=True)
    expect(dialog.get_by_role('button', name='Synthetic unknown', exact=False)).to_be_visible()
    expect(dialog.get_by_role('button', name='Synthetic accepted', exact=False)).to_have_count(0)


def test_failed_proposal_keeps_input_and_recovery_guidance(page, server):
    create_project(page, server)
    page.get_by_role('button', name='Advanced: add fact', exact=True).click()
    page.get_by_label('Title', exact=True).fill('Synthetic unsent proposal')
    page.get_by_label('Body', exact=True).fill('Preserve this input on failure.')
    page.route('**/api/changes', lambda route: route.abort('failed'))
    page.get_by_role('button', name='Preview proposal', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('could not be reached')
    expect(page.get_by_label('Body', exact=True)).to_have_value('Preserve this input on failure.')
    expect(page.get_by_role('button', name='Preview proposal', exact=True)).to_be_enabled()
    page.unroute('**/api/changes')
    page.get_by_role('button', name='Preview proposal', exact=True).click()
    expect(page.get_by_role('heading', name='Review proposed change')).to_be_visible()


def test_visual_evidence_and_no_external_asset_requests(page, server, tmp_path):
    """Supplemental render evidence; assertions characterize established behavior."""
    import os
    from pathlib import Path
    output = Path(os.environ.get('KH_UI_ARTIFACTS', str(tmp_path / 'captures')))
    output.mkdir(parents=True, exist_ok=True)
    requests = []
    errors = []
    page.on('request', lambda request: requests.append(request.url))
    page.on('pageerror', lambda error: errors.append(str(error)))
    create_project(page, server)
    seed(page, server, 'How registered knowledge changes',
         'Keep accepted knowledge readable. Inspect the consequences of a correction before it changes the project.\n\n'
         'A proposal brings the new wording, its evidence and its registered dependencies together. A human accepts or rejects that proposal explicitly.\n\n'
         'When a basis changes, registered dependent topics are marked for review. Unregistered relationships are not assessed. This is a synthetic verification topic, not bundled knowledge.',
         evidence=[{'kind': 'document', 'locator': 'https://example.com/synthetic-guide', 'label': 'Synthetic review guide'}], kind='concept')
    seed(page, server, 'Project boundaries', 'A synthetic decision.', kind='decision')
    seed(page, server, 'What needs further evidence?', 'A synthetic unresolved question.', kind='question')
    page.reload()
    expect(page.locator('#content h1')).to_contain_text('Library')
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='How registered knowledge changes', exact=False).click()
    page.screenshot(path=str(output / 'desktop.png'), full_page=True)
    page.get_by_role('button', name='Propose a change', exact=True).click()
    page.screenshot(path=str(output / 'proposal.png'), full_page=True)
    page.get_by_label('Body', exact=True).fill('A revised synthetic basis.')
    page.get_by_role('button', name='Preview proposal', exact=True).click()
    expect(page.get_by_role('heading', name='Review proposed change')).to_be_in_viewport()
    page.screenshot(path=str(output / 'review.png'), full_page=True)
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='How registered knowledge changes', exact=False).click()
    page.set_viewport_size({'width': 390, 'height': 850})
    page.screenshot(path=str(output / 'mobile.png'), full_page=True)
    page.get_by_role('button', name='Activity', exact=False).click()
    expect(page.get_by_role('dialog', name='Activity', exact=True)).to_be_visible()
    page.screenshot(path=str(output / 'mobile-activity.png'), full_page=True)
    assert not errors
    assert all(url.startswith(server) for url in requests)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('destination', ['Library', 'Settings'])
def test_late_warehouse_response_does_not_replace_destination(page, server, destination):
    create_project(page, server)
    seed(page, server, 'Synthetic delayed topic', 'Shared local knowledge.')
    page.evaluate("""() => {
      const original = window.fetch;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (String(args[0]).endsWith('/warehouse')) {
          document.documentElement.dataset.delayed = 'true';
          await new Promise(resolve => { window.releaseWarehouse = resolve; });
        }
        return response;
      };
    }""")
    page.get_by_role('button', name='Warehouse', exact=True).click()
    expect(page.locator('html')).to_have_attribute('data-delayed', 'true')
    page.get_by_role('button', name=destination, exact=True).click()
    expect(page.locator('#content h1')).to_have_text(destination)
    page.evaluate('window.releaseWarehouse()')
    page.wait_for_timeout(150)
    expect(page.locator('#content h1')).to_have_text(destination)
    expect(page.get_by_role('button', name=destination, exact=True)).to_have_attribute('aria-current', 'page')


def test_narrow_activity_dialog_closes_with_escape_and_keeps_utilities_available(page, server):
    page.set_viewport_size({'width': 390, 'height': 850})
    login(page, server)
    toggle = page.get_by_role('button', name='Activity', exact=False)
    expect(toggle).to_have_attribute('aria-haspopup', 'dialog')
    toggle.click()
    expect(page.get_by_role('dialog', name='Activity', exact=True)).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.get_by_role('dialog')).to_have_count(0)
    expect(toggle).to_be_focused()
    expect(page.get_by_role('button', name='Settings', exact=True)).to_be_visible()
    page.get_by_role('button', name='Settings', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Settings')
    expect(page.get_by_role('button', name='Back to Library', exact=True)).to_be_visible()


def test_unauthenticated_launch_is_actionable(page, server):
    page.goto(server)
    expect(page.get_by_role('heading', name='Open Knowledge Hub from the desktop app')).to_be_visible()
    expect(page.get_by_role('button', name='New project', exact=True)).to_have_count(0)
