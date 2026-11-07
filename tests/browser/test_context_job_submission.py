"""Production context submission; only the native chooser/provider boundaries are synthetic."""
from playwright.sync_api import expect
from test_reader import page, server, login


def test_selected_native_context_submits_a_durable_job_without_capture_upload(page, server, tmp_path):
    from knowledge_hub.context_sources import ContextSources
    source = tmp_path / 'synthetic-context.txt'
    source.write_text('Synthetic sky is blue.')
    selected = ContextSources(server.store.path.parent).register_selected([source])[0]
    page.add_init_script("window.pywebview = {api: {choose_context_sources: async () => ({cancelled:false,sources:" + __import__('json').dumps([selected]) + "})}}")
    login(page, server)
    page.get_by_role('button', name='Attach files or local context', exact=True).click()
    expect(page.get_by_text('synthetic-context.txt', exact=True)).to_be_visible()
    page.get_by_label('Capture', exact=True).fill('Understand this selected synthetic source')
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('heading', name='Curator work', exact=True)).to_be_visible()
    jobs = page.request.get(server + '/api/curator-jobs').json()['jobs']
    assert len(jobs) == 1
    assert page.request.get(server + '/api/captures').json()['captures'] == []
    assert str(source) not in page.locator('#content').inner_text()
    page.reload()
    page.get_by_role('button', name='Activity', exact=True).click()
    page.get_by_role('button', name='Open Curator work ' + jobs[0]['id'][:8], exact=True).click()
    expect(page.get_by_role('heading', name='Curator work', exact=True)).to_be_visible()
    page.get_by_role('button', name='Cancel Curator work', exact=True).click()
    expect(page.get_by_role('main').get_by_role('status')).to_contain_text('cancelled')
