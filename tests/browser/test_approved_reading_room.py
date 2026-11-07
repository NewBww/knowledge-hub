"""Approved reading room through production HTTP, isolated stores and real Chrome."""
from pathlib import Path
import os
import pytest
from playwright.sync_api import expect
from test_reader import page, server, login, seed
from test_first_release_ui import seed_book


def test_single_attachment_control_and_bounded_multiline(page, server):
    login(page, server)
    expect(page.locator('input[webkitdirectory]')).to_have_count(0)
    expect(page.get_by_role('button', name='Attach files or local context', exact=True)).to_be_visible()
    expect(page.locator('.intention-field')).not_to_be_visible()
    text = page.get_by_label('Capture', exact=True)
    text.fill('Synthetic first line')
    text.press('Shift+Enter')
    text.press('a')
    expect(text).to_have_value('Synthetic first line\na')
    text.dispatch_event('keydown', {'key': 'Enter', 'isComposing': True})
    assert page.request.get(server + '/api/captures').json()['captures'] == []
    text.fill('\n'.join(['Synthetic bounded line'] * 80))
    dimensions = text.evaluate('(n) => ({height:n.clientHeight,scroll:n.scrollHeight,overflow:getComputedStyle(n).overflowY})')
    assert dimensions['height'] <= 180
    assert dimensions['scroll'] > dimensions['height']
    assert dimensions['overflow'] == 'auto'
    expect(page.get_by_role('button', name='Send', exact=True)).to_be_in_viewport()
    page.reload()
    expect(text).to_have_value('\n'.join(['Synthetic bounded line'] * 80))
    text.fill('Synthetic saved request\nwith a second line')
    text.press('Enter')
    expect(page.locator('#content h1')).to_have_text('Review capture')
    saved = page.request.get(server + '/api/captures').json()['captures']
    assert len(saved) == 1
    assert page.request.get(server + '/api/captures/' + saved[0]['id']).json()['text'] == 'Synthetic saved request\nwith a second line'
    assert page.request.get(server + '/api/warehouse').json()['items'] == []


def test_library_search_opens_without_moving_rows_and_composer_is_docked(page, server):
    login(page, server)
    seed_book(page, server)
    page.reload()
    entry = page.locator('.book-entry')
    expect(entry).to_be_visible()
    before = entry.bounding_box()
    page.get_by_role('button', name='Search Library', exact=True).click()
    expect(page.get_by_role('searchbox', name='Search Library', exact=True)).to_be_visible()
    after = entry.bounding_box()
    assert before == after
    composer = page.locator('.capture-composer')
    assert composer.evaluate('(n) => getComputedStyle(n.parentElement).position') == 'fixed'
    search = page.get_by_role('searchbox', name='Search Library', exact=True)
    search.fill('absent reading room')
    expect(entry).to_have_count(0)
    search.fill('synthetic first')
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('A synthetic first page')


def test_warehouse_is_responsive_grid_of_real_records(page, server):
    login(page, server)
    for number in range(4):
        seed(page, server, f'Synthetic warehouse {number}', f'Synthetic body {number}')
    page.get_by_role('button', name='Warehouse', exact=True).click()
    cards = page.locator('#warehouse-results .warehouse-card')
    expect(cards).to_have_count(4)
    assert cards.nth(1).bounding_box()['x'] > cards.nth(0).bounding_box()['x']
    cards.nth(2).click()
    expect(page.locator('#content h1')).to_have_text('Synthetic warehouse 2')
    expect(page.get_by_text('Synthetic body 2', exact=True)).to_be_visible()


def select_passage(page):
    page.locator('#content [data-section-id] .prose').first.evaluate('''node => {
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      const nodes = []; let current; while ((current = walker.nextNode())) nodes.push(current);
      const range = document.createRange(); let offset = 0;
      for (const text of nodes) {
        if (offset <= 2 && offset + text.length > 2) range.setStart(text, 2 - offset);
        if (offset < 20 && offset + text.length >= 20) { range.setEnd(text, 20 - offset); break; }
        offset += text.length;
      }
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
      document.dispatchEvent(new Event('selectionchange'));
    }''')


def test_reader_personal_marks_context_draft_and_history_recover(page, server):
    login(page, server)
    _, fact, change = seed_book(page, server)
    page.reload()
    page.locator('#content').get_by_role('button', name='Open Synthetic reader handbook', exact=True).click()
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    expect(page.get_by_text('1 page total', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Show outline', exact=True)).to_have_count(0)
    prose = page.locator('#content [data-section-id] .prose').first
    initial = prose.bounding_box()
    page.get_by_role('button', name='Review', exact=False).click()
    assert prose.bounding_box() == initial
    page.get_by_role('button', name='Close review', exact=True).click()
    select_passage(page)
    page.get_by_role('button', name='Highlight', exact=True).click()
    expect(page.locator('.personal-highlight')).to_have_text('readable synthetic')
    page.reload()
    expect(page.locator('#content h1')).to_have_text('A synthetic first page')
    expect(page.locator('.personal-highlight')).to_have_text('readable synthetic')
    select_passage(page)
    page.get_by_role('button', name='Ask', exact=True).click()
    expect(page.locator('#passage-ask')).to_be_visible()
    page.get_by_label('Passage request', exact=True).fill('Please clarify this exact phrase.')
    page.get_by_role('button', name='Close passage request', exact=True).click()
    page.get_by_role('button', name='Library', exact=True).click()
    page.go_back()
    expect(page.locator('#content h1')).to_have_text('A synthetic first page')
    page.get_by_role('button', name='Resume passage request', exact=True).click()
    expect(page.get_by_label('Passage request', exact=True)).to_have_value('Please clarify this exact phrase.')
    page.get_by_role('button', name='Send passage request', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Review capture')
    saved = page.request.get(server + '/api/captures').json()['captures']
    detail = page.request.get(server + '/api/captures/' + saved[0]['id']).json()
    assert detail['request_context']['passage'] == 'readable synthetic'
    assert detail['request_context']['page_revision'] == 1
    assert page.request.get(server + '/api/warehouse/' + fact['id']).json()['revision'] == fact['revision']


def test_local_source_chip_uses_production_routes_and_revokes_without_paths(page, server, tmp_path):
    from knowledge_hub.context_sources import ContextSources
    folder = tmp_path / 'synthetic-context'
    folder.mkdir()
    (folder / 'note.txt').write_text('Synthetic scoped context only')
    sources = ContextSources(tmp_path)
    registered = sources.register_selected([folder])[0]
    login(page, server)
    chip = page.get_by_role('list', name='Authorized local context', exact=True)
    expect(chip).to_contain_text('synthetic-context')
    expect(chip).to_contain_text('directory · active')
    assert str(folder) not in page.content()
    assert page.request.get(server + '/api/context-sources/' + registered['id']).json()['status'] == 'active'
    chip.get_by_role('button', name='Revoke synthetic-context', exact=True).click()
    expect(chip).to_contain_text('directory · revoked')
    assert page.request.get(server + '/api/context-sources/' + registered['id']).json()['status'] == 'revoked'
