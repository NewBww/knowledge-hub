import pytest
from playwright.sync_api import expect
from test_reader import page, server, login, seed


def prepare_change(page, server):
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
    expect(page.locator('#content h1')).to_have_text('Review proposed change')
    return source


@pytest.mark.parametrize('boundary', ['verification', 'decision', 'refresh'])
@pytest.mark.parametrize(('decision', 'destination'), [
    ('Approve', 'Needs attention'), ('Reject', 'Activity'),
    ('Approve', 'Settings'), ('Reject', 'Settings'),
])
def test_decision_verification_cannot_replace_newer_navigation(page, server, decision, destination, boundary):
    source = prepare_change(page, server)
    held = []
    requests = []
    pattern = ('**/api/changes/*/' + decision.lower()) if boundary == 'decision' else '**/api/changes'
    method = 'POST' if boundary == 'decision' else 'GET'

    def hold(route):
        if route.request.method != method:
            return route.continue_()
        requests.append(route.request)
        if held or (boundary == 'refresh' and len(requests) != 2):
            return route.continue_()
        response = route.fetch()
        assert response.ok
        held.append((route, response))
        page.evaluate("document.documentElement.dataset.decisionHeld = 'true'")

    # Hold a real committed POST or canonical readback, never an invented body.
    # A DOM marker polls the controlled boundary without unsafe-eval under CSP.
    page.route(pattern, hold)
    page.get_by_role('button', name=decision + ' change', exact=True).click()
    expect(page.locator('html')).to_have_attribute('data-decision-held', 'true')
    page.get_by_role('button', name=destination, exact=False).click()
    expect(page.locator('#content h1')).to_have_text(destination)
    if destination == 'Settings':
        page.get_by_label('Model', exact=True).fill('synthetic-unsaved-model')
    assert len(held) == 1
    held[0][0].fulfill(response=held[0][1])
    expect(page.locator('#status')).to_have_text('Change approved' if decision == 'Approve' else 'Change rejected')
    expect(page.locator('#content h1')).to_have_text(destination)
    if destination == 'Settings':
        expect(page.get_by_label('Model', exact=True)).to_have_value('synthetic-unsaved-model')
    item = page.request.get(server + '/api/warehouse/' + source['id']).json()
    assert item['body'] == ('Corrected basis.' if decision == 'Approve' else 'Original basis.')
    changes = page.request.get(server + '/api/changes').json()['changes']
    assert not any(change['status'] == 'pending' for change in changes)
    expect(page.locator('#review-count')).to_have_text('')


def test_approval_library_readback_cannot_replace_newer_navigation(page, server):
    prepare_change(page, server)
    held = []

    def hold(route):
        response = route.fetch()
        assert response.ok
        held.append((route, response))

    page.route('**/api/library/books', hold)
    with page.expect_request('**/api/library/books'):
        page.get_by_role('button', name='Approve change', exact=True).click()
    page.get_by_role('button', name='Needs attention', exact=True).click()
    expect(page.locator('#content h1')).to_have_text('Needs attention')
    assert len(held) == 1
    held[0][0].fulfill(response=held[0][1])
    expect(page.locator('#status')).to_have_text('Change approved')
    expect(page.locator('#content h1')).to_have_text('Needs attention')
    expect(page.get_by_role('button', name='Synthetic dependent', exact=False)).to_be_visible()


def test_approval_readback_cannot_replace_newer_attention_navigation(page, server):
    source = prepare_change(page, server)
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
