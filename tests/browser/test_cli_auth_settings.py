"""Full CLI handoff from production create_app; no fixture adapter or sign-in."""
import shlex

import pytest
from playwright.sync_api import expect
from test_reader import page, server


@pytest.mark.parametrize('provider', ['chatgpt', 'copilot', 'opencode', 'gemini', 'hermes'])
def test_settings_renders_every_isolated_auth_command_and_working_directory(page, server, provider):
    server.connections.discover = lambda name: '/synthetic bin/' + name
    page.goto(server + '/#token=synthetic-browser-human')
    expect(page.locator('#content h1')).to_have_text('Your knowledge starts here')
    page.get_by_role('button', name='Settings', exact=True).click()
    page.get_by_label('Connection', exact=True).select_option(provider)
    with page.expect_response('**/api/curator/auth/start') as response:
        page.get_by_role('button', name='Sign-in instructions', exact=True).click()
    actual = response.value.json()
    expect(page.get_by_text('Working directory', exact=True)).to_be_visible()
    expect(page.get_by_label('Sign-in working directory', exact=True)).to_have_text(actual['cwd'])
    commands = page.get_by_label('Sign-in commands', exact=True)
    expect(commands).to_have_text('\n'.join([actual['cwd_command'], *actual['display_commands']]))
    # Assert exact source text, including quoting, not whitespace-normalized presentation.
    assert commands.text_content() == '\n'.join([actual['cwd_command'], *actual['display_commands']])
    assert shlex.split(commands.text_content().splitlines()[0]) == ['cd', '--', actual['cwd']]
    expect(page.get_by_text(actual['reason'], exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Enable processing', exact=True)).to_be_disabled()
    assert page.request.get(server + '/api/curator').json()['enabled'] is False
    if provider == 'hermes':
        assert len(actual['display_commands']) == 2
        assert '--provider nous --host 127.0.0.1' in commands.text_content()
    if provider == 'chatgpt':
        expect(page.get_by_text('Inference remains blocked: deny-all tool execution has not been verified.', exact=True)).to_be_visible()
    else:
        expect(page.get_by_text('After sign-in, confirm the connection/model and disclosure, run the synthetic connection check, then explicitly enable processing.', exact=True)).to_be_visible()
    expect(page.get_by_text('CLI execution remains blocked until isolated operation and synthetic readback are verified.', exact=True)).to_have_count(0)
