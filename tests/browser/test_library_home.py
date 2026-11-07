"""Whole-home Library acceptance against production create_app and real Chrome."""
from pathlib import Path
from playwright.sync_api import expect
from test_reader import page, server, login, seed
from test_first_release_ui import seed_book


def test_library_is_the_whole_home_not_a_rail_destination(page, server):
    login(page, server)
    expect(page.locator('.rail')).to_have_count(0)
    expect(page.locator('#context-index')).not_to_be_visible()
    expect(page.get_by_role('button', name='Add knowledge', exact=True)).to_have_count(0)
    expect(page.get_by_label('Capture', exact=True)).to_be_visible()
    seed_book(page, server)
    page.reload()
    expect(page.locator('#content h1')).to_have_text('Library')
    expect(page.locator('#context-index')).not_to_be_visible()
    expect(page.locator('.book-entry')).to_have_count(1)
    expect(page.locator('.book-entry img')).to_have_count(0)
    expect(page.get_by_label('Capture', exact=True)).to_be_visible()
    for name in ['Activity', 'Needs attention', 'Warehouse', 'Settings']:
        expect(page.get_by_role('button', name=name, exact=False)).to_be_visible()


def test_one_composer_hides_native_pickers_and_sends_with_ime_safe_enter(page, server):
    login(page, server)
    expect(page.get_by_label('Attach files', exact=True)).not_to_be_visible()
    expect(page.get_by_label('Choose folder', exact=True)).not_to_be_visible()
    expect(page.get_by_role('button', name='Save capture locally', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Clear draft', exact=True)).not_to_be_visible()
    text = page.get_by_label('Capture', exact=True)
    text.fill('Synthetic first line')
    text.press('Shift+Enter')
    text.press('a')
    expect(text).to_have_value('Synthetic first line\na')
    text.dispatch_event('keydown', {'key': 'Enter', 'isComposing': True})
    assert page.request.get(server + '/api/captures').json()['captures'] == []
    text.press('Enter')
    expect(page.locator('#content h1')).to_have_text('Review capture')
    captures = page.request.get(server + '/api/captures').json()['captures']
    assert len(captures) == 1
    saved = page.request.get(server + '/api/captures/' + captures[0]['id']).json()
    assert saved['text'] == 'Synthetic first line\na'


def test_activity_and_attention_are_dismissible_dialogs_that_preserve_home_draft(page, server):
    login(page, server)
    text = page.get_by_label('Capture', exact=True)
    text.fill('Synthetic unfinished home draft')
    for name in ['Activity', 'Needs attention']:
        trigger = page.get_by_role('button', name=name, exact=False)
        trigger.click()
        dialog = page.get_by_role('dialog', name=name, exact=True)
        expect(dialog).to_be_visible()
        expect(dialog.get_by_role('heading', name=name, exact=True)).to_be_visible()
        page.keyboard.press('Escape')
        expect(dialog).to_have_count(0)
        expect(trigger).to_be_focused()
        expect(text).to_have_value('Synthetic unfinished home draft')
    page.get_by_role('button', name='Activity', exact=False).click()
    page.get_by_role('button', name='Close Activity', exact=True).click()
    expect(text).to_have_value('Synthetic unfinished home draft')


def test_home_search_finds_readable_pages_without_a_persistent_index(page, server):
    login(page, server)
    seed_book(page, server)
    page.reload()
    page.get_by_role('button', name='Search Library', exact=True).click()
    search = page.get_by_role('searchbox', name='Search Library', exact=True)
    search.fill('no synthetic match')
    expect(page.locator('.book-entry')).to_have_count(0)
    expect(page.get_by_text('No books or pages match your search.', exact=True)).to_be_visible()
    search.fill('synthetic first')
    page.get_by_role('button', name='Read A synthetic first page', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('A synthetic first page')


def test_attention_dialog_search_stays_filtered_to_uncertain_knowledge(page, server):
    login(page, server)
    seed(page, server, 'Synthetic accepted', 'Accepted body.')
    seed(page, server, 'Synthetic question', 'An unresolved question.', kind='question')
    page.get_by_role('button', name='Needs attention', exact=True).click()
    dialog = page.get_by_role('dialog', name='Needs attention', exact=True)
    dialog.get_by_role('searchbox').fill('Synthetic')
    expect(dialog.get_by_role('button', name='Synthetic question', exact=False)).to_be_visible()
    expect(dialog.get_by_role('button', name='Synthetic accepted', exact=False)).to_have_count(0)
    dialog.get_by_role('searchbox').fill('absent')
    expect(dialog.get_by_text('No topics match your search.', exact=True)).to_be_visible()
