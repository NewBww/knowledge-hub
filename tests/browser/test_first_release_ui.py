"""First-release real-browser acceptance; synthetic local stores only."""
from test_reader import page, server, login, workspace
from playwright.sync_api import expect
import pytest


def test_capture_reviews_multiple_files_and_clipboard_images(page, server):
    create_workspace(page, server)
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_label('Capture', exact=True).fill('Synthetic capture draft')
    page.get_by_label('Attach files', exact=True).set_input_files([
        {'name': 'notes.txt', 'mimeType': 'text/plain', 'buffer': b'Synthetic text'},
        {'name': 'unsupported.xyz', 'mimeType': 'application/octet-stream', 'buffer': b'Synthetic unknown'}])
    expect(page.get_by_text('notes.txt', exact=True)).to_be_visible()
    expect(page.get_by_text('unsupported.xyz', exact=True)).to_be_visible()
    expect(page.locator('input[webkitdirectory]')).to_have_count(0)
    expect(page.get_by_role('button', name='Attach files or local context', exact=True)).to_have_count(1)
    page.get_by_role('button', name='Remove notes.txt', exact=True).click()
    expect(page.get_by_text('notes.txt', exact=True)).to_have_count(0)
    page.get_by_label('Capture', exact=True).dispatch_event('paste', {'clipboardData': None})
    page.evaluate("""() => {
      const data = new DataTransfer();
      data.items.add(new File([new Uint8Array([137,80,78,71])], 'clipboard.png', {type: 'image/png'}));
      document.querySelector('[name=capture]').dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true}));
    }""")
    expect(page.get_by_text('clipboard.png', exact=True)).to_be_visible()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Synthetic capture draft')
    expect(page.get_by_text('Saved locally · reviewed by you', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Send', exact=True)).to_be_enabled()




def seed_book(page, server, approve=True):
    from test_reader import seed
    import uuid
    fact = seed(page, server, 'Synthetic shared basis', 'Canonical support is shared, not copied.')
    project = workspace(page, server)
    page_id, book_id, section_id = [str(uuid.uuid4()) for _ in range(3)]
    response = page.request.post(f"{server}/api/library/changes", data={
        'base_revision': project['revision'], 'idempotency_key': str(uuid.uuid4()), 'summary': 'Synthetic reader guide',
        'operations': [
            {'op': 'upsert_page', 'id': page_id, 'base_revision': 0, 'title': 'A synthetic first page', 'state': 'published',
             'sections': [{'id': section_id, 'kind': 'factual', 'body': 'A readable synthetic explanation.',
                           'supports': [{'item_id': fact['id'], 'revision': fact['revision'], 'relationship': 'supports'}]}], 'links': []},
            {'op': 'upsert_book', 'id': book_id, 'base_revision': 0, 'title': 'Synthetic reader handbook',
             'purpose': 'Read with registered support', 'overview': 'Synthetic local-only browser fixture.',
             'state': 'published', 'page_ids': [page_id]}]})
    assert response.ok, response.text()
    change = response.json()
    if approve:
        response = page.request.post(f"{server}/api/library/changes/{change['id']}/approve")
        assert response.ok, response.text()
    return project, fact, change


def test_library_opens_real_book_pages_and_inspects_shared_support(page, server):
    create_workspace(page, server)
    project, fact, change = seed_book(page, server)
    page.reload()
    expect(page.get_by_role('heading', name='Library', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='A synthetic first page', exact=True)).to_have_count(0)
    page.locator('#content').get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Synthetic reader handbook')
    expect(page.get_by_text('Synthetic local-only browser fixture.', exact=True)).to_be_visible()
    expect(page.get_by_text('Read with registered support', exact=True)).to_be_visible()
    page.locator('#content').get_by_role('button', name='Read A synthetic first page', exact=True).click()
    expect(page.get_by_role('heading', name='A synthetic first page', exact=True)).to_be_visible()
    expect(page.get_by_text('A readable synthetic explanation.', exact=True)).to_be_visible()
    expect(page.locator('#breadcrumb')).to_contain_text('Synthetic reader handbook')
    expect(page.get_by_role('button', name='Inspect Synthetic shared basis', exact=True)).to_be_visible()
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_role('button', name='Search Library', exact=True).click()
    page.get_by_role('searchbox', name='Search Library', exact=True).fill('zzzz')
    expect(page.get_by_text('No books or pages match your search.', exact=True)).to_be_visible()
    page.get_by_role('searchbox', name='Search Library', exact=True).fill('synthetic first')
    expect(page.get_by_role('button', name='A synthetic first page', exact=False)).to_be_visible()
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    page.get_by_role('button', name='Inspect Synthetic shared basis', exact=True).click()
    expect(page.get_by_role('heading', name='Synthetic shared basis', exact=True)).to_be_visible()
    expect(page.get_by_text('Canonical support is shared, not copied.', exact=True)).to_be_visible()


def test_library_proposal_requires_human_diff_review_before_publication(page, server):
    create_workspace(page, server)
    project, fact, change = seed_book(page, server, approve=False)
    page.get_by_role('button', name='Activity', exact=False).click()
    page.get_by_role('button', name='Library: Synthetic reader guide', exact=False).click()
    expect(page.get_by_role('heading', name='Review Library change', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='Before', exact=True)).to_have_count(2)
    expect(page.get_by_text('A readable synthetic explanation.', exact=True)).to_be_visible()
    expect(page.get_by_text('Supports: Synthetic shared basis · revision 1', exact=True)).to_be_visible()
    assert page.request.get(f"{server}/api/library/books").json()['books'] == []
    page.get_by_role('button', name='Approve Library change', exact=True).click()
    expect(page.get_by_role('heading', name='A synthetic first page', exact=True)).to_be_visible()
    assert page.request.get(f"{server}/api/library/changes").json()['changes'][0]['status'] == 'approved'


def test_capture_save_inspects_real_extraction_and_discards_locally(page, server):
    create_workspace(page, server)
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_label('Capture', exact=True).fill('Synthetic private capture')
    page.get_by_label('Attach files', exact=True).set_input_files([
        {'name': 'notes.txt', 'mimeType': 'text/plain', 'buffer': b'Synthetic extracted note'},
        {'name': 'archive.zip', 'mimeType': 'application/zip', 'buffer': b'not an archive'}])
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('heading', name='Review capture', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Activity', exact=False)).to_be_visible()
    expect(page.get_by_text('Synthetic extracted note', exact=True)).to_be_visible()
    expect(page.get_by_text('unsupported_media_type', exact=False)).to_be_visible()
    expect(page.get_by_role('button', name='Process this snapshot', exact=True)).to_have_count(0)
    expect(page.get_by_role('heading', name='Awaiting agent', exact=True)).to_be_visible()
    project = workspace(page, server)
    response = page.request.get(f"{server}/api/captures")
    assert response.ok, response.text()
    assert len(response.json()['captures']) == 1
    page.get_by_role('button', name='Discard capture', exact=True).click()
    expect(page.get_by_role('heading', name='Your draft', exact=True)).to_be_visible()
    assert page.request.get(f"{server}/api/captures").json()['captures'] == []








def test_intake_restores_unsaved_draft_and_saved_capture_after_navigation(page, server):
    create_workspace(page, server)
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_label('Capture', exact=True).fill('Synthetic retained draft')
    page.get_by_label('Attach files', exact=True).set_input_files({'name': 'draft.txt', 'mimeType': 'text/plain', 'buffer': b'Draft attachment'})
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Synthetic retained draft')
    expect(page.get_by_text('draft.txt', exact=True)).to_be_visible()
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('heading', name='Review capture', exact=True)).to_be_visible()
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('')
    page.get_by_role('button', name='Activity', exact=False).click()
    page.get_by_role('button', name='Review saved capture', exact=False).click()
    expect(page.get_by_text('Synthetic retained draft', exact=True)).to_be_visible()
    expect(page.get_by_text('Draft attachment', exact=True)).to_be_visible()


def test_empty_book_has_keyboard_accessible_overview_and_persistent_home(page, server):
    import uuid
    create_workspace(page, server)
    project = workspace(page, server)
    book_id = str(uuid.uuid4())
    response = page.request.post(f"{server}/api/library/changes", data={
        'base_revision': project['revision'], 'idempotency_key': str(uuid.uuid4()), 'summary': 'Synthetic empty book',
        'operations': [{'op': 'upsert_book', 'id': book_id, 'base_revision': 0,
                        'title': 'A book awaiting pages', 'purpose': 'A deliberate reading destination',
                        'overview': 'An overview without a first page.', 'state': 'published', 'page_ids': []}]})
    assert response.ok, response.text()
    change = response.json()
    assert page.request.post(f"{server}/api/library/changes/{change['id']}/approve").ok
    page.reload()
    expect(page.locator('#content h1')).to_have_text('Library')
    index_book = page.locator('#content').get_by_role('button', name='Open A book awaiting pages', exact=True)
    expect(index_book).to_be_visible()
    index_book.focus()
    page.keyboard.press('Enter')
    expect(page.locator('#content h1')).to_have_text('A book awaiting pages')
    expect(page.locator('#reader')).to_be_focused()
    expect(page.get_by_text('An overview without a first page.', exact=True)).to_be_visible()
    expect(page.get_by_text('No pages in this book yet.', exact=False)).to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 850})
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Library')
    page.locator('#content').get_by_role('button', name='Open A book awaiting pages', exact=True).click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_be_visible()
    page.get_by_role('button', name='Settings', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Settings')
    expect(page.locator('.index')).not_to_be_visible()
    page.get_by_role('button', name='Back to Library', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Library')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [320, 861, 1024, 1440])
def test_library_book_settings_and_intake_fit_window(page, server, width):
    """Supplemental characterization across the shipped breakpoints."""
    create_workspace(page, server)
    seed_book(page, server)
    page.reload()
    expect(page.locator('#content h1')).to_have_text('Library')
    page.set_viewport_size({'width': width, 'height': 850})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#content').get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#content').get_by_role('button', name='Read A synthetic first page', exact=True).click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Library', exact=True).click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Settings', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Settings')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_library_pending_count_is_correct_on_initial_project_open(page, server):
    create_workspace(page, server)
    seed_book(page, server, approve=False)
    page.reload()
    expect(page.locator('#review-count')).to_have_text('1')


def test_image_attachment_can_be_visually_reviewed_before_local_save(page, server):
    from io import BytesIO
    from PIL import Image
    image = BytesIO()
    Image.new('RGB', (1200, 800), 'blue').save(image, format='PNG')
    create_workspace(page, server)
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_label('Attach files', exact=True).set_input_files({'name': 'synthetic.png', 'mimeType': 'image/png', 'buffer': image.getvalue()})
    preview = page.get_by_role('img', name='Preview synthetic.png', exact=True)
    expect(preview).to_be_visible()
    assert preview.evaluate('img => img.complete && img.naturalWidth === 1200')
    assert preview.bounding_box()['width'] <= page.locator('#content').bounding_box()['width']
    page.get_by_role('button', name='Remove synthetic.png', exact=True).click()
    expect(preview).to_have_count(0)


@pytest.mark.parametrize('view', ['Warehouse', 'Activity'])
def test_late_fact_response_does_not_replace_library_intake(page, server, view):
    create_workspace(page, server)
    page.evaluate("""() => {
      const original = window.fetch;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (String(args[0]).endsWith('/warehouse')) {
          document.documentElement.dataset.warehouseDelayed = 'true';
          await new Promise(resolve => { window.releaseWarehouse = resolve; });
        }
        return response;
      };
    }""")
    page.get_by_role('button', name=view, exact=False).click()
    expect(page.locator('html')).to_have_attribute('data-warehouse-delayed', 'true')
    if view == 'Activity':
        page.keyboard.press('Escape')
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_label('Capture', exact=True).fill('Keep this synthetic draft visible')
    page.evaluate('window.releaseWarehouse()')
    page.wait_for_timeout(100)
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Keep this synthetic draft visible')
    expect(page.get_by_role('button', name='Library', exact=True)).to_have_attribute('aria-current', 'page')


def test_browser_folder_drop_is_rejected_without_enumeration_or_capture(page, server):
    """Folder bulk upload was retired; browser mode must fail closed instead."""
    create_workspace(page, server)
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.locator('input[webkitdirectory]')).to_have_count(0)
    expect(page.get_by_role('button', name='Attach files or local context', exact=True)).to_have_count(1)
    expect(page.get_by_text('Browser: files only; folders require the desktop app.', exact=True)).to_be_visible()
    page.get_by_label('Capture', exact=True).fill('Synthetic preserved folder-drop draft')
    page.evaluate("""() => {
      document.documentElement.dataset.folderEnumerated = 'false';
      const event = new Event('drop', {bubbles:true, cancelable:true});
      Object.defineProperty(event, 'dataTransfer', {value: {
        items:[{webkitGetAsEntry:() => ({isDirectory:true, createReader:() => {
          document.documentElement.dataset.folderEnumerated = 'true'; throw new Error('Must not enumerate');
        }})}],
        get files() { document.documentElement.dataset.folderEnumerated = 'true'; throw new Error('Must not read files'); }
      }});
      document.querySelector('.capture-composer').dispatchEvent(event);
    }""")
    expect(page.get_by_role('alert')).to_contain_text('No folder contents were read')
    expect(page.locator('html')).to_have_attribute('data-folder-enumerated', 'false')
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Synthetic preserved folder-drop draft')
    expect(page.get_by_role('list', name='Review attachments', exact=True).locator('li')).to_have_count(0)
    assert page.request.get(server + '/api/captures').json()['captures'] == []
    assert page.request.get(server + '/api/warehouse').json()['items'] == []


def test_first_release_render_evidence_local_requests_and_narrow_layout(page, server, tmp_path):
    """Supplemental evidence of already-tested real routes, not inference quality."""
    import os
    from pathlib import Path
    output = Path(os.environ.get('KH_FIRST_RELEASE_UI_ARTIFACTS', str(tmp_path / 'first-release-captures')))
    output.mkdir(parents=True, exist_ok=True)
    def shot(name):
        page.evaluate('document.activeElement.blur(); window.scrollTo(0, 0)')
        page.wait_for_timeout(80)
        page.screenshot(path=str(output / name), full_page=True)
    errors, requests = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append(request.url))
    create_workspace(page, server)
    seed_book(page, server)
    page.set_viewport_size({'width': 1440, 'height': 960})
    page.reload()
    expect(page.locator('#content h1')).to_have_text('Library')
    shot('library-desktop.png')
    page.locator('#content').get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    shot('book-desktop.png')
    page.locator('#content').get_by_role('button', name='Read A synthetic first page', exact=True).click()
    shot('page-desktop.png')
    page.get_by_role('button', name='Library', exact=True).click()
    page.set_viewport_size({'width': 390, 'height': 850})
    shot('library-mobile.png')
    page.get_by_role('button', name='Activity', exact=False).click()
    expect(page.get_by_role('dialog', name='Activity', exact=True)).to_be_visible()
    shot('library-mobile-activity.png')
    page.keyboard.press('Escape')
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_label('Capture', exact=True).fill('Synthetic notes for a readable field guide.\n\nThe local queue waits for your connected agent; Knowledge Hub does not run models.')
    page.get_by_label('Attach files', exact=True).set_input_files([
        {'name': 'synthetic-field-notes.md', 'mimeType': 'text/markdown', 'buffer': b'Synthetic file content for local extraction.'},
        {'name': 'a-very-long-synthetic-filename-' + 'unbroken' * 10 + '.zip', 'mimeType': 'application/zip', 'buffer': b'Unsupported synthetic attachment'}])
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    shot('add-knowledge-mobile.png')
    page.set_viewport_size({'width': 1440, 'height': 960})
    shot('add-knowledge-desktop.png')
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('heading', name='Review capture', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Enable agent capture access', exact=True)).to_be_disabled()
    page.evaluate('window.scrollTo(0, 0)')
    shot('capture-review.png')
    page.get_by_role('button', name='Settings', exact=True).click()
    expect(page.locator('.index')).not_to_be_visible()
    expect(page.locator('#topics')).not_to_contain_text('No saved captures.')
    expect(page.get_by_role('heading', name='External agent', exact=True)).to_be_visible()
    page.get_by_role('button', name='Check for Updates', exact=True).click()
    expect(page.get_by_text('Update source not configured', exact=True)).to_be_visible()
    shot('settings-desktop.png')
    page.set_viewport_size({'width': 390, 'height': 850})
    shot('settings-mobile.png')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width': 1440, 'height': 960})
    seed_book(page, server, approve=False)
    page.get_by_role('button', name='Activity', exact=False).click()
    page.get_by_role('button', name='Library: Synthetic reader guide', exact=False).click()
    expect(page.get_by_role('heading', name='Review Library change', exact=True)).to_be_visible()
    shot('library-review.png')
    assert not errors
    assert all(url.startswith(server) or url.startswith('data:image/') for url in requests)
    assert page.evaluate('localStorage.length') == 0


def test_settings_global_permission_requires_human_consent_and_revokes(page, server):
    create_workspace(page, server)
    page.get_by_role('button', name='Settings', exact=True).click()
    enable = page.get_by_role('button', name='Enable agent capture access', exact=True)
    expect(enable).to_be_disabled()
    page.get_by_label('I understand my harness may send all captures in the shared workspace to its models', exact=True).check()
    enable.click()
    expect(page.get_by_role('button', name='Disable agent capture access', exact=True)).to_be_visible()
    assert page.request.get(server + '/api/agent/access').json()['enabled'] is True
    page.get_by_role('button', name='Disable agent capture access', exact=True).click()
    expect(page.get_by_role('button', name='Enable agent capture access', exact=True)).to_be_disabled()
    assert page.request.get(server + '/api/agent/access').json()['enabled'] is False


def test_agent_setup_keeps_external_mcp_equal_without_duplicate_provider_login(page, server):
    create_workspace(page, server)
    page.get_by_role('button', name='Settings', exact=True).click()
    expect(page.get_by_role('heading', name='External agent', exact=True)).to_be_visible()
    expect(page.locator('pre')).to_contain_text('Contents/MacOS/Knowledge Hub')
    expect(page.locator('pre')).to_contain_text('mcp')
    expect(page.get_by_text('A connected harness may send selected data to cloud models. Knowledge Hub cannot guarantee downstream training or retention policy.', exact=True)).to_be_visible()
    expect(page.get_by_label('Ingestion model', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Processing settings', exact=True)).to_have_count(0)


@pytest.mark.parametrize(('decision', 'retain'), [('approve', False), ('reject', False), ('approve', True)])
def test_external_agent_queue_result_requires_human_access_and_review(page, server, decision, retain):
    page.set_viewport_size({'width': 1440, 'height': 960})
    from knowledge_hub.curator import Curator
    from knowledge_hub.core import DomainError
    create_workspace(page, server)
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_role('heading', name='External agent access', exact=True)).to_have_count(0)
    page.get_by_label('Capture', exact=True).fill('Synthetic source for external MCP agent')
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('heading', name='Awaiting agent', exact=True)).to_be_visible()
    project = workspace(page, server)
    agent = Curator(server.store)
    with pytest.raises(DomainError):
        agent.capture_list(project['id'])
    enable = page.get_by_role('button', name='Enable agent capture access', exact=True)
    expect(enable).to_be_disabled()
    page.get_by_label('I understand my harness may send all captures in the shared workspace to its models', exact=True).check()
    enable.click()
    expect(page.get_by_text('Agent capture access enabled. This does not prove a harness is connected.', exact=True)).to_be_visible()
    queued = agent.capture_list(project['id'])['captures']
    assert len(queued) == 1
    capture = queued[0]
    page.get_by_role('button', name='Disable agent capture access', exact=True).click()
    expect(page.get_by_text('Agent capture access is disabled. Your intake stays queued locally.', exact=True)).to_be_visible()
    with pytest.raises(DomainError):
        agent.capture_get(project['id'], capture['id'])
    page.get_by_label('I understand my harness may send all captures in the shared workspace to its models', exact=True).check()
    page.get_by_role('button', name='Enable agent capture access', exact=True).click()
    expect(page.get_by_role('button', name='Disable agent capture access', exact=True)).to_be_visible()
    if decision == 'approve' and not retain: evidence_capture(page, 'capture-authorized.png')
    source = agent.capture_get(project['id'], capture['id'], max_chars=100)
    assert source['text'] == 'Synthetic source for external MCP agent'
    claim = agent.claim(project['id'], capture['id'], 'Synthetic test agent', capture['snapshot_sha256'], project['revision'])
    from knowledge_hub.curator import CurationSubmission
    agent.curation_submit(project['id'], capture['id'], CurationSubmission.model_validate({
        'snapshot_sha256': capture['snapshot_sha256'], 'claim_token': claim['claim_token'], 'base_revision': project['revision'],
        'summary': 'Synthetic externally organized capture', 'operations': [
            {'op': 'upsert', 'title': 'Synthetic agent fact', 'body': 'A proposal submitted by an external-agent service test, not a model run.', 'kind': 'fact', 'evidence': [], 'depends_on': []}],
        'library_suggestions': [{'book_title': 'Synthetic agent book', 'page_title': 'Synthetic agent page', 'body': 'Suggested destination, not published.'}]}))
    assert server.store.knowledge(project['id'])['items'] == []
    page.get_by_role('button', name='Refresh agent result', exact=True).click()
    expect(page.get_by_role('heading', name='Agent proposals', exact=True)).to_be_visible()
    expect(page.get_by_text('Synthetic agent book → Synthetic agent page', exact=True)).to_be_visible()
    expect(page.locator('#review-count')).to_have_text('1')
    page.get_by_role('button', name='Activity', exact=False).click()
    expect(page.get_by_role('dialog').get_by_text('Ready for review', exact=True)).to_be_visible()
    page.get_by_role('dialog').get_by_role('button', name='Review saved capture', exact=False).click()
    expect(page.get_by_role('heading', name='Agent proposals', exact=True)).to_be_visible()
    if decision == 'approve' and not retain: evidence_capture(page, 'agent-proposals.png')
    page.get_by_role('button', name='Review Warehouse proposal', exact=True).click()
    expect(page.get_by_role('heading', name='Review proposed change', exact=True)).to_be_visible()
    expect(page.get_by_text('New topic — no accepted content yet.', exact=True)).to_be_visible()
    if decision == 'approve' and not retain: evidence_capture(page, 'agent-review.png')
    if retain:
        page.get_by_label('Keep original capture until its expiry', exact=True).check()
    page.get_by_role('button', name='Approve change' if decision == 'approve' else 'Reject change', exact=True).click()
    if decision == 'approve':
        expect(page.get_by_role('heading', name='Arrange Library pages', exact=True)).to_be_visible()
        preview = page.get_by_role('button', name='Preview Library proposal', exact=True)
        expect(preview).to_be_disabled()
        page.get_by_label('Cite Synthetic agent fact for Synthetic agent page', exact=True).check()
        preview.click()
        expect(page.get_by_role('heading', name='Review Library change', exact=True)).to_be_visible()
        expect(page.get_by_text('Suggested destination, not published.', exact=True)).to_be_visible()
        assert len(page.request.get(f"{server}/api/captures").json()['captures']) == 1
        page.get_by_role('button', name='Approve Library change', exact=True).click()
        expect(page.locator('#content h1')).to_have_text('Synthetic agent page')
        books = page.request.get(f"{server}/api/library/books").json()['books']
        book = page.request.get(f"{server}/api/library/books/{books[0]['id']}").json()
        fact = server.store.knowledge(project['id'])['items'][0]
        assert book['pages'][0]['sections'][0]['supports'][0]['item_id'] == fact['id']
        assert book['pages'][0]['sections'][0]['supports'][0]['revision'] == fact['revision']
    else:
        expect(page.locator('#status')).to_have_text('Change rejected')
        assert server.store.knowledge(project['id'])['items'] == []
    captures = page.request.get(f"{server}/api/captures").json()['captures']
    assert len(captures) == (1 if retain else 0)
    if retain:
        page.get_by_role('button', name='Activity', exact=False).click()
        expect(page.get_by_text('Accepted · source retained until expiry', exact=True)).to_be_visible()
        page.locator('#content').get_by_role('button', name='Review saved capture', exact=False).click()
        expect(page.get_by_role('heading', name='Accepted', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='Arrange suggested Library pages', exact=True)).to_have_count(0)


def evidence_capture(page, name):
    import os
    from pathlib import Path
    target = os.environ.get('KH_FIRST_RELEASE_UI_ARTIFACTS')
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        page.evaluate('document.activeElement.blur(); window.scrollTo(0, 0)')
        page.wait_for_timeout(80)
        page.screenshot(path=str(Path(target) / name), full_page=True)


def create_workspace(page, server):
    login(page, server)


def test_library_home_composer_replaces_separate_add_knowledge_navigation(page, server):
    create_workspace(page, server)
    expect(page.get_by_role('button', name='Library', exact=True)).to_have_attribute('aria-current', 'page')
    expect(page.locator('#content h1')).to_have_text('Your knowledge starts here')
    expect(page.get_by_role('button', name='Curator', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Agent setup', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Your knowledge starts here')
    expect(page.get_by_role('button', name='Add knowledge', exact=True)).to_have_count(0)
    expect(page.get_by_role('searchbox')).not_to_be_visible()
    expect(page.get_by_role('button', name='Library', exact=True)).to_have_attribute('aria-current', 'page')
    expect(page.get_by_label('Capture', exact=True)).to_be_visible()
    expect(page.get_by_label('Title', exact=True)).to_have_count(0)
    page.get_by_label('Capture', exact=True).fill('Retained within Library')
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Your knowledge starts here')
    page.get_by_role('button', name='Warehouse', exact=True).click()
    expect(page.get_by_role('heading', name='Warehouse', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Advanced: add fact', exact=True)).to_be_visible()
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Retained within Library')
