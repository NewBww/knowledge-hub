from playwright.sync_api import expect
from test_reader import page, server, login, seed


def test_approval_readback_cannot_replace_newer_attention_navigation(page, server):
    login(page, server)
    source = seed(page, server, 'Synthetic basis', 'Original basis.')
    seed(page, server, 'Synthetic dependent', 'Depends on basis.', depends_on=[source['id']])
    page.reload()
    page.get_by_role('button', name='Warehouse', exact=True).click()
    page.get_by_role('button', name='Synthetic basis', exact=False).click()
    page.get_by_role('button', name='Propose a change', exact=True).click()
    page.get_by_label('Body', exact=True).fill('Corrected basis.')
    page.get_by_label('Source label', exact=True).fill('Synthetic document')
    page.get_by_label('Source locator', exact=True).fill('https://example.com/basis')
    page.get_by_label('Evidence kind', exact=True).select_option('document')
    page.get_by_role('button', name='Preview proposal', exact=True).click()
    held = []
    def hold(route):
        held.append((route, route.fetch()))
    page.route('**/api/warehouse/' + source['id'], hold)
    with page.expect_request('**/api/warehouse/' + source['id']):
        page.get_by_role('button', name='Approve change', exact=True).click()
    page.get_by_role('button', name='Needs attention', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Needs attention')
    assert len(held) == 1
    held[0][0].fulfill(response=held[0][1])
    expect(page.locator('#status')).to_have_text('Change approved')
    expect(page.locator('#content h1')).to_have_text('Needs attention')
    expect(page.get_by_role('button', name='Synthetic dependent', exact=False)).to_be_visible()
