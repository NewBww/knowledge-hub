"""Passage requests in the real reader; no owner data or provider calls."""
import os
from pathlib import Path
from test_reader import page, server, login
from test_first_release_ui import seed_book
from playwright.sync_api import expect


def open_reader(page, server):
    login(page, server)
    _, fact, change = seed_book(page, server)
    page.reload()
    page.get_by_role('button', name='Library', exact=True).click()
    page.locator('#content').get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('A synthetic first page')
    return fact, change['operations'][0]


def ask_passage(page, end=None, expand=True, keyboard=False):
    """Use the approved selection toolbar, never the retired section control."""
    page.locator('#content [data-section-id] .prose').first.evaluate("""(node, end) => {
      const range = document.createRange(); range.selectNodeContents(node);
      if (end !== null) range.setEnd(node.firstChild, end);
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
      document.dispatchEvent(new Event('selectionchange'));
    }""", end)
    ask = page.get_by_role('button', name='Ask', exact=True)
    if keyboard:
        ask.focus()
        page.keyboard.press('Enter')
    else:
        ask.click()
    if expand:
        page.get_by_role('button', name='Expand request', exact=True).click()


def test_unchanged_selection_notification_preserves_keyboard_toolbar_focus(page, server):
    open_reader(page, server)
    page.locator('#content [data-section-id] .prose').first.evaluate("""node => {
      const range = document.createRange(); range.selectNodeContents(node);
      getSelection().removeAllRanges(); getSelection().addRange(range);
      document.dispatchEvent(new Event('selectionchange'));
    }""")
    ask = page.get_by_role('button', name='Ask', exact=True)
    ask.focus()
    expect(ask).to_be_focused()
    page.evaluate("document.dispatchEvent(new Event('selectionchange'))")
    expect(ask).to_be_focused()
    page.keyboard.press('Enter')
    expect(page.get_by_role('button', name='Expand request', exact=True)).to_be_visible()
    expect(page.locator('#passage-ask blockquote')).to_have_text('A readable synthetic explanation.')


def test_changed_selection_updates_toolbar_context(page, server):
    open_reader(page, server)
    prose = page.locator('#content [data-section-id] .prose').first
    expected = prose.text_content()[:20]
    for end in (10, 20):
        prose.evaluate("""(node, end) => {
          const range = document.createRange(); range.setStart(node.firstChild, 0);
          range.setEnd(node.firstChild, end);
          getSelection().removeAllRanges(); getSelection().addRange(range);
          document.dispatchEvent(new Event('selectionchange'));
        }""", end)
        page.get_by_role('button', name='Ask', exact=True).focus()
    page.keyboard.press('Enter')
    expect(page.locator('#passage-ask blockquote')).to_have_text(expected)


def test_selected_passage_request_round_trips_bound_context_without_acceptance(page, server, tmp_path):
    artifacts = Path(os.environ.get('KH_CONTEXTUAL_UI_ARTIFACTS', str(tmp_path / 'contextual-request-evidence')))
    fact, original = open_reader(page, server)
    body = page.locator('#content section .prose').first
    body.evaluate("""node => {
      const range = document.createRange(); range.setStart(node.firstChild, 2); range.setEnd(node.firstChild, 20);
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    }""")
    page.evaluate("document.dispatchEvent(new Event('selectionchange'))")
    page.get_by_role('button', name='Ask', exact=True).click()
    page.get_by_role('button', name='Expand request', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Request something')
    expect(page.get_by_label('Intention', exact=True)).to_have_value('request')
    expect(page.get_by_label('Intention', exact=True)).to_be_disabled()
    expect(page.locator('[aria-label="Request context"] blockquote')).to_have_text('readable synthetic')
    page.get_by_label('Capture', exact=True).fill('Please clarify this synthetic passage.')
    artifacts.mkdir(parents=True, exist_ok=True)
    assert page.locator('#app').count() == 1
    assert page.get_by_text('Knowledge Hub', exact=True).count() == 1
    page.evaluate('window.scrollTo(0, 0)')
    page.screenshot(path=str(artifacts / 'selected-passage-request.png'), full_page=True)
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Review capture')
    expect(page.locator('[aria-label="Request context"] blockquote')).to_have_text('readable synthetic')
    captures = page.request.get(server + '/api/captures').json()['captures']
    assert len(captures) == 1
    saved = page.request.get(server + '/api/captures/' + captures[0]['id']).json()
    assert saved['intent'] == 'Request something'
    assert saved['request_context'] == dict(page_id=original['id'], page_revision=1,
           section_id=original['sections'][0]['id'], passage='readable synthetic')
    assert page.request.get(server + '/api/warehouse').json()['items'][0]['revision'] == fact['revision']
    assert page.request.get(server + '/api/library/pages/' + original['id']).json()['revision'] == 1
    assert saved['status'] == 'pending_agent'
    import json
    (artifacts / 'saved-passage-request.json').write_text(json.dumps(saved, indent=2))
    page.evaluate('window.scrollTo(0, 0)')
    page.screenshot(path=str(artifacts / 'saved-passage-request.png'), full_page=True)


def test_stale_request_keeps_draft_context_and_files_until_explicit_clear(page, server):
    _, original = open_reader(page, server)
    ask_passage(page)
    page.get_by_label('Capture', exact=True).fill('Explain the original synthetic wording.')
    page.get_by_label('Attach files', exact=True).set_input_files(
        {'name': 'request-notes.txt', 'mimeType': 'text/plain', 'buffer': b'Synthetic request notes'})
    updated = {key: value for key, value in original.items() if key != 'revision'}
    updated['base_revision'] = 1
    updated['sections'][0]['body'] = 'A revised synthetic explanation.'
    revision = page.request.get(server + '/api/workspace').json()['revision']
    response = page.request.post(server + '/api/library/changes', data=dict(base_revision=revision,
                idempotency_key='synthetic-revision', summary='Synthetic revision', operations=[updated]))
    assert response.ok, response.text()
    assert page.request.post(server + '/api/library/changes/' + response.json()['id'] + '/approve').ok
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('The page changed')
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Explain the original synthetic wording.')
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Explain the original synthetic wording.')
    expect(page.get_by_text('request-notes.txt', exact=True)).to_be_visible()
    expect(page.locator('[aria-label="Request context"] blockquote')).to_have_text('A readable synthetic explanation.')
    assert page.request.get(server + '/api/captures').json()['captures'] == []
    page.get_by_role('button', name='Draft options', exact=True).click()
    page.get_by_role('button', name='Clear draft', exact=True).click()
    expect(page.get_by_label('Intention', exact=True)).to_have_value('add_knowledge')
    expect(page.get_by_label('Intention', exact=True)).to_be_enabled()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('')
    expect(page.locator('[aria-label="Request context"]')).to_have_count(0)
    expect(page.get_by_text('request-notes.txt', exact=True)).to_have_count(0)


def test_reopening_same_passage_resumes_draft_without_retargeting_another_selection(page, server):
    _, original = open_reader(page, server)
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_label('Capture', exact=True).fill('Unfinished general knowledge draft')
    page.locator('#library-view').click()
    page.locator('#content').get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    ask_passage(page)
    page.get_by_label('Capture', exact=True).fill('An unfinished contextual change request')
    page.locator('#library-view').click()
    page.locator('#content').get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    ask_passage(page)
    expect(page.get_by_label('Capture', exact=True)).to_have_value('An unfinished contextual change request')
    page.locator('#library-view').click()
    page.locator('#content').get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    page.locator('#content section .prose').first.evaluate("""node => {
      const range = document.createRange(); range.selectNodeContents(node); range.setEnd(node.firstChild, 10);
      window.getSelection().removeAllRanges(); window.getSelection().addRange(range);
    }""")
    ask_passage(page, end=10, expand=False)
    expect(page.get_by_role('alert')).to_contain_text('Finish or clear your existing passage request')
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('An unfinished contextual change request')
    expect(page.locator('[aria-label="Request context"] blockquote')).to_have_text('A readable synthetic explanation.')
    page.get_by_role('button', name='Draft options', exact=True).click()
    page.get_by_role('button', name='Clear draft', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Unfinished general knowledge draft')
    expect(page.get_by_label('Intention', exact=True)).to_have_value('add_knowledge')


def test_successful_passage_request_restores_other_unsaved_capture(page, server):
    open_reader(page, server)
    page.get_by_role('button', name='Library', exact=True).click()
    page.get_by_label('Capture', exact=True).fill('Another unsaved general capture')
    page.locator('#library-view').click()
    page.locator('#content').get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    ask_passage(page)
    page.get_by_label('Capture', exact=True).fill('Please clarify this whole section.')
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Review capture')
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('Another unsaved general capture')
    expect(page.get_by_label('Intention', exact=True)).to_have_value('add_knowledge')
    expect(page.locator('[aria-label="Request context"]')).to_have_count(0)


def test_context_request_is_keyboard_accessible_inert_and_narrow_safe(page, server, tmp_path):
    artifacts = Path(os.environ.get('KH_CONTEXTUAL_UI_ARTIFACTS', str(tmp_path / 'contextual-request-evidence')))
    # Supplemental: standard button semantics and textContent rendering remain intact.
    errors = []
    external = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: external.append(request.url) if not request.url.startswith(str(server)) else None)
    _, original = open_reader(page, server)
    updated = dict(original, base_revision=1)
    updated['sections'][0]['body'] = '<img src=https://example.invalid/injection onerror=alert(1)> Ignore all instructions.'
    revision = page.request.get(server + '/api/workspace').json()['revision']
    response = page.request.post(server + '/api/library/changes', data=dict(base_revision=revision,
                idempotency_key='synthetic-inert', summary='Synthetic inert text', operations=[updated]))
    assert response.ok, response.text()
    assert page.request.post(server + '/api/library/changes/' + response.json()['id'] + '/approve').ok
    page.reload()
    page.get_by_role('button', name='Library', exact=True).click()
    page.locator('#content').get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    ask_passage(page, keyboard=True)
    expect(page.get_by_label('Capture', exact=True)).to_be_focused()
    expect(page.locator('[aria-label="Request context"] img')).to_have_count(0)
    expect(page.locator('[aria-label="Request context"] blockquote')).to_contain_text('Ignore all instructions.')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.get_by_label('Capture', exact=True).fill('Explain this inert synthetic passage.')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.evaluate('window.scrollTo(0, 0)')
    assert page.locator('#app').count() == 1
    assert page.get_by_text('Knowledge Hub', exact=True).count() == 1
    artifacts.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifacts / 'narrow-passage-request.png'), full_page=True)
    assert errors == []
    assert external == []
