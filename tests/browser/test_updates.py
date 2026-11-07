"""Real Settings update-state check; no configured publisher or invented latest version."""
from test_reader import page, server, login
from knowledge_hub.version import VERSION
from playwright.sync_api import expect


def test_settings_update_check_is_honest_without_a_release_source(page, server):
    login(page, server)
    page.get_by_role('button', name='Settings', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Settings')
    expect(page.get_by_role('heading', name='Agent setup', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Back to Library', exact=True)).to_be_visible()
    expect(page.locator('.toolbar').get_by_role('button', name='Check for Updates', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Check for Updates', exact=True).click()
    expect(page.get_by_role('heading', name='Application updates', exact=True)).to_be_visible()
    expect(page.get_by_text('Update source not configured', exact=True)).to_be_visible()
    expect(page.get_by_text(f'Installed version: {VERSION}', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Update unavailable', exact=True)).to_be_disabled()
    expect(page.get_by_text('You are up to date', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Check again', exact=True).click()
    expect(page.get_by_text('Update source not configured', exact=True)).to_be_visible()
    assert page.request.get(server + '/api/workspace').json()['item_count'] == 0
    page.get_by_role('button', name='Back to Library', exact=True).click()
    expect(page.get_by_role('heading', name='Your knowledge starts here', exact=True)).to_be_visible()
    expect(page.locator('#search')).to_be_disabled()
    expect(page.locator('.index')).not_to_be_visible()
    expect(page.get_by_role('button', name='Library', exact=True)).to_have_attribute('aria-current', 'page')
    expect(page.locator('#topics')).not_to_contain_text('One MCP connection')


def test_settings_check_hands_off_to_native_dialog_without_inventing_latest_version(page, server):
    class NativeBoundary:
        calls = 0

        def check_for_updates(self):
            self.calls += 1

    native = NativeBoundary()
    server.updater.native = native
    login(page, server)
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_role('button', name='Check for Updates', exact=True).click()
    expect(page.get_by_text('Native update window opened', exact=True)).to_be_visible()
    expect(page.get_by_text('Release hosting has not been selected.', exact=False)).to_have_count(0)
    expect(page.get_by_role('button', name='Update unavailable')).to_have_count(0)
    expect(page.get_by_text('Save unsaved capture drafts and stop your harness’s Knowledge Hub MCP connection before installing. Restart and installation are confirmed in the native window.', exact=True)).to_be_visible()
    assert native.calls == 1
    page.get_by_role('button', name='Check again', exact=True).click()
    expect(page.get_by_text('Native update window opened', exact=True)).to_be_visible()
    assert native.calls == 2
    page.get_by_role('button', name='Back to Library', exact=True).click()
    expect(page.get_by_role('heading', name='Your knowledge starts here', exact=True)).to_be_visible()
    expect(page.locator('#search')).to_be_disabled()
    expect(page.locator('.index')).not_to_be_visible()
    expect(page.get_by_role('button', name='Library', exact=True)).to_have_attribute('aria-current', 'page')
    expect(page.locator('#topics')).not_to_contain_text('One MCP connection')
