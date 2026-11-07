"""Selected-context boundaries against the production factory and real HTTP."""
import json

import pytest
from playwright.sync_api import expect
from test_reader import page, server, login


def select_context(page, server, tmp_path):
    from knowledge_hub.context_sources import ContextSources
    source = tmp_path / 'selected-synthetic.txt'
    source.write_text('Synthetic sky is blue.')
    selected = ContextSources(server.store.path.parent).register_selected([source])[0]
    page.add_init_script('window.pywebview = {api: {choose_context_sources: async () => ('
                         + json.dumps({'cancelled': False, 'sources': [selected]}) + ')}}')
    login(page, server)
    page.get_by_role('button', name='Attach files or local context', exact=True).click()
    expect(page.get_by_label('Use local context ' + selected['name'], exact=True)).to_be_checked()
    return selected


def hold_job_response(page, endpoint='/api/curator-jobs'):
    """Hold an actual response, and mark completion after actual detail JSON consumption."""
    page.evaluate("""endpoint => {
      const original = window.fetch;
      let held = false;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (String(args[0]).endsWith('/retry') && args[1]?.method === 'POST') {
          document.body.dataset.retryCommitted = JSON.stringify(await response.clone().json());
        }
        if ((args[0] === endpoint || (endpoint === 'detail' && String(args[0]).startsWith('/api/curator-jobs/') && !args[1]?.method)) && !held) {
          held = true;
          document.body.dataset.jobHeld = 'true';
          await new Promise(resolve => { window.releaseJob = resolve; });
        }
        if (String(args[0]).startsWith('/api/curator-jobs/') && !args[1]?.method) {
          const originalJSON = response.json.bind(response);
          response.json = async () => {
            const data = await originalJSON();
            setTimeout(() => { document.body.dataset.jobRead = 'true'; }, 0);
            return data;
          };
        }
        return response;
      };
    }""", endpoint)


@pytest.mark.parametrize('endpoint', ['/api/curator-jobs', 'detail'], ids=['post', 'readback'])
def test_late_job_submission_preserves_newer_intention_draft(page, server, tmp_path, endpoint):
    selected = select_context(page, server, tmp_path)
    instruction = 'Understand selected synthetic source'
    page.get_by_label('Capture', exact=True).fill(instruction)
    hold_job_response(page, endpoint)
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.locator('body')).to_have_attribute('data-job-held', 'true')
    jobs = page.request.get(server + '/api/curator-jobs').json()['jobs']
    assert len(jobs) == 1
    assert [ref['source_id'] for ref in jobs[0]['source_references']] == [selected['id']]
    page.get_by_role('button', name='Warehouse', exact=True).click()
    expect(page.get_by_role('heading', name='Warehouse', exact=True)).to_be_visible()
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value(instruction)
    page.get_by_role('button', name='Draft options', exact=True).click()
    page.get_by_label('Intention', exact=True).select_option('request')
    page.get_by_role('button', name='Draft options', exact=True).click()
    page.evaluate('window.releaseJob()')
    expect(page.locator('body')).to_have_attribute('data-job-read', 'true')
    expect(page.get_by_label('Capture', exact=True)).to_have_value(instruction)
    assert page.get_by_role('heading', name='Curator work', exact=True).count() == 0
    page.reload()
    expect(page.get_by_label('Capture', exact=True)).to_have_value(instruction)
    page.get_by_role('button', name='Draft options', exact=True).click()
    expect(page.get_by_label('Intention', exact=True)).to_have_value('request')
    expect(page.get_by_label('Use local context ' + selected['name'], exact=True)).to_be_checked()
    assert len(page.request.get(server + '/api/curator-jobs').json()['jobs']) == 1
    assert page.request.get(server + '/api/captures').json()['captures'] == []


def test_authorized_unselected_context_and_picker_cancel_preserve_selection(page, server, tmp_path):
    from knowledge_hub.context_sources import ContextSources
    other = tmp_path / 'unselected-synthetic.txt'
    other.write_text('Synthetic private context must not be attached implicitly.')
    unselected = ContextSources(server.store.path.parent).register_selected([other])[0]
    selected = select_context(page, server, tmp_path)
    other_box = page.get_by_label('Use local context ' + unselected['name'], exact=True)
    expect(other_box).not_to_be_checked()
    instruction = 'Use only the selected synthetic source'
    page.get_by_label('Capture', exact=True).fill(instruction)
    page.evaluate('window.pywebview.api.choose_context_sources = async () => ({cancelled: true, sources: []})')
    page.get_by_role('button', name='Attach files or local context', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value(instruction)
    expect(page.get_by_label('Use local context ' + selected['name'], exact=True)).to_be_checked()
    expect(other_box).not_to_be_checked()
    page.reload()
    expect(page.get_by_label('Capture', exact=True)).to_have_value(instruction)
    expect(page.get_by_label('Use local context ' + selected['name'], exact=True)).to_be_checked()
    expect(other_box).not_to_be_checked()
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('heading', name='Curator work', exact=True)).to_be_visible()
    jobs = page.request.get(server + '/api/curator-jobs').json()['jobs']
    assert len(jobs) == 1
    assert [ref['source_id'] for ref in jobs[0]['source_references']] == [selected['id']]
    assert str(other) not in page.locator('#content').inner_text()


def test_revoked_selection_fails_closed_without_losing_recovered_draft(page, server, tmp_path):
    selected = select_context(page, server, tmp_path)
    instruction = 'Retain this synthetic draft after revocation'
    page.get_by_label('Capture', exact=True).fill(instruction)
    page.get_by_role('button', name='Revoke ' + selected['name'], exact=True).click()
    selected_box = page.get_by_label('Use local context ' + selected['name'], exact=True)
    expect(selected_box).to_be_disabled()
    assert page.request.get(server + '/api/context-sources/' + selected['id']).json()['status'] == 'revoked'
    page.reload()
    expect(page.get_by_label('Capture', exact=True)).to_have_value(instruction)
    expect(selected_box).to_be_disabled()
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('alert')).to_be_visible()
    expect(page.get_by_label('Capture', exact=True)).to_have_value(instruction)
    assert page.request.get(server + '/api/curator-jobs').json()['jobs'] == []
    assert page.request.get(server + '/api/captures').json()['captures'] == []


def test_ambiguous_transport_retry_after_reload_reuses_durable_job(page, server, tmp_path):
    selected = select_context(page, server, tmp_path)
    instruction = 'Synthetic idempotent transport retry'
    page.get_by_label('Capture', exact=True).fill(instruction)
    page.evaluate("""() => {
      const original = window.fetch;
      let lost = false;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (args[0] === '/api/curator-jobs' && args[1]?.method === 'POST' && !lost) {
          lost = true;
          await response.clone().json();
          throw new TypeError('Synthetic response lost after real commit');
        }
        return response;
      };
    }""")
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('Your input is preserved')
    original_jobs = page.request.get(server + '/api/curator-jobs').json()['jobs']
    assert len(original_jobs) == 1
    page.reload()
    expect(page.get_by_label('Capture', exact=True)).to_have_value(instruction)
    expect(page.get_by_label('Use local context ' + selected['name'], exact=True)).to_be_checked()
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('heading', name='Curator work', exact=True)).to_be_visible()
    jobs = page.request.get(server + '/api/curator-jobs').json()['jobs']
    assert [job['id'] for job in jobs] == [original_jobs[0]['id']]
    assert page.request.get(server + '/api/captures').json()['captures'] == []
    page.get_by_role('button', name='Library', exact=True).click()
    expect(page.get_by_label('Capture', exact=True)).to_have_value('')


def seed_job(page, server, tmp_path, *, review_ready=False):
    """Persist real jobs/proposals without inference or provider/auth stores.

    A future fixture clock fences the production host worker out of this job;
    only this fixture claims it and exercises the normal checkpoint/publication.
    """
    from knowledge_hub.context_sources import ContextSources
    from knowledge_hub.curator_jobs import ContextJobSources, CuratorJobs
    from knowledge_hub.shared import SharedWarehouse

    class SyntheticPolicy:
        def state(self):
            return dict(connection='synthetic', model='synthetic-model',
                        generation='synthetic-generation', profile_id='synthetic-profile',
                        enabled=True, consent=True, status='checked')

    native = ContextSources(server.store.path.parent)
    source = tmp_path / 'job-fixture.txt'
    source.write_text('Synthetic proposal source.')
    selected = native.register_selected([source])[0]
    jobs = CuratorJobs(server.store, sources=ContextJobSources(native),
                       connections=SyntheticPolicy(), clock=lambda: 10**12)
    job = jobs.submit([selected['id']], 'Synthetic navigation fixture',
                      'synthetic-navigation-fixture', human=True)
    lease = jobs.claim('synthetic-fixture-worker')
    assert lease['id'] == job['id']
    if review_ready:
        scope = SharedWarehouse(server.store).scope()
        jobs.checkpoint(lease, dict(
            base_revision=page.request.get(server + '/api/workspace').json()['revision'],
            idempotency_key='synthetic-navigation-proposal', summary='Synthetic review fixture',
            operations=[dict(op='upsert', title='Synthetic pending knowledge',
                             body='Synthetic pending body.', kind='fact')]))
        job = jobs.publish(lease, scope)
        assert server.store.changes(scope)[0]['status'] == 'pending'
        assert server.store.knowledge(scope)['items'] == []
    else:
        job = jobs.failure(lease, 'requires_connection')
        assert job['status'] == 'blocked'
    assert page.request.get(server + '/api/curator-jobs/' + job['id']).json() == jobs.get(job['id'])
    page.get_by_role('button', name='Activity', exact=True).click()
    page.get_by_role('button', name='Open Curator work ' + job['id'][:8], exact=True).click()
    expect(page.get_by_role('heading', name='Curator work', exact=True)).to_be_visible()
    return job


def test_late_job_proposal_review_does_not_replace_settings(page, server, tmp_path):
    login(page, server)
    job = seed_job(page, server, tmp_path, review_ready=True)
    # Hold the real canonical proposal-list response, never a fabricated payload.
    page.evaluate("""() => {
      const original = window.fetch;
      window.fetch = async (...args) => {
        const response = await original(...args);
        if (args[0] === '/api/changes') {
          document.body.dataset.reviewHeld = 'true';
          await new Promise(resolve => { window.releaseReview = resolve; });
          const originalJSON = response.json.bind(response);
          response.json = async () => {
            const data = await originalJSON();
            setTimeout(() => { document.body.dataset.reviewRead = 'true'; }, 0);
            return data;
          };
        }
        return response;
      };
    }""")
    page.get_by_role('button', name='Review proposed knowledge', exact=True).click()
    expect(page.locator('body')).to_have_attribute('data-review-held', 'true')
    page.get_by_role('button', name='Settings', exact=True).click()
    expect(page.get_by_role('heading', name='Settings', exact=True)).to_be_visible()
    page.get_by_label('Model', exact=True).fill('synthetic-unsaved-review-model')
    page.evaluate('window.releaseReview()')
    expect(page.locator('body')).to_have_attribute('data-review-read', 'true')
    expect(page.get_by_role('heading', name='Settings', exact=True)).to_be_visible()
    expect(page.get_by_label('Model', exact=True)).to_have_value('synthetic-unsaved-review-model')
    assert page.get_by_role('heading', name='Review proposed change', exact=True).count() == 0
    changes = page.request.get(server + '/api/changes').json()['changes']
    assert [(change['id'], change['status']) for change in changes] == [(job['result']['change_id'], 'pending')]
    assert page.request.get(server + '/api/warehouse').json()['items'] == []


@pytest.mark.parametrize('endpoint', ['retry', 'detail'])
def test_late_job_retry_does_not_replace_settings(page, server, tmp_path, endpoint):
    """Characterize the existing refresh-closure guard at both real HTTP seams."""
    login(page, server)
    job = seed_job(page, server, tmp_path)
    retry_path = '/api/curator-jobs/' + job['id'] + '/retry'
    hold_job_response(page, retry_path if endpoint == 'retry' else 'detail')
    page.get_by_role('button', name='Retry Curator work', exact=True).click()
    expect(page.locator('body')).to_have_attribute('data-job-held', 'true')
    retried = json.loads(page.locator('body').get_attribute('data-retry-committed'))
    assert retried['id'] == job['id']
    assert retried['status'] == 'queued'
    assert retried['error'] is None
    assert retried['attempt_count'] == job['attempt_count']
    expect(page.locator('body')).to_have_attribute('data-job-held', 'true')
    page.get_by_role('button', name='Settings', exact=True).click()
    expect(page.get_by_role('heading', name='Settings', exact=True)).to_be_visible()
    page.get_by_label('Model', exact=True).fill('synthetic-unsaved-retry-model')
    page.evaluate('window.releaseJob()')
    expect(page.locator('body')).to_have_attribute('data-job-read', 'true')
    expect(page.get_by_role('heading', name='Settings', exact=True)).to_be_visible()
    expect(page.get_by_label('Model', exact=True)).to_have_value('synthetic-unsaved-retry-model')
    assert page.get_by_role('heading', name='Curator work', exact=True).count() == 0
    # The host may already have blocked the queued retry on its absent connection.
    saved = page.request.get(server + '/api/curator-jobs/' + job['id']).json()
    assert saved['status'] in {'queued', 'running', 'blocked'}
    assert [entry['id'] for entry in page.request.get(server + '/api/curator-jobs').json()['jobs']] == [job['id']]
    assert page.request.get(server + '/api/changes').json()['changes'] == []


def test_job_proposal_review_still_opens_without_navigation(page, server, tmp_path):
    login(page, server)
    job = seed_job(page, server, tmp_path, review_ready=True)
    page.get_by_role('button', name='Review proposed knowledge', exact=True).click()
    expect(page.get_by_role('heading', name='Review proposed change', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='Synthetic pending knowledge', exact=True)).to_be_visible()
    changes = page.request.get(server + '/api/changes').json()['changes']
    assert [(change['id'], change['status']) for change in changes] == [(job['result']['change_id'], 'pending')]
    assert page.request.get(server + '/api/warehouse').json()['items'] == []


def test_late_cancel_readback_does_not_replace_settings(page, server, tmp_path):
    select_context(page, server, tmp_path)
    page.get_by_label('Capture', exact=True).fill('Synthetic cancellable job')
    page.get_by_role('button', name='Send', exact=True).click()
    expect(page.get_by_role('heading', name='Curator work', exact=True)).to_be_visible()
    job = page.request.get(server + '/api/curator-jobs').json()['jobs'][0]
    hold_job_response(page, '/api/curator-jobs/' + job['id'] + '/cancel')
    page.get_by_role('button', name='Cancel Curator work', exact=True).click()
    expect(page.locator('body')).to_have_attribute('data-job-held', 'true')
    assert page.request.get(server + '/api/curator-jobs/' + job['id']).json()['status'] == 'cancelled'
    page.get_by_role('button', name='Settings', exact=True).click()
    expect(page.get_by_role('heading', name='Settings', exact=True)).to_be_visible()
    page.get_by_label('Model', exact=True).fill('synthetic-unsaved-model')
    page.evaluate('window.releaseJob()')
    expect(page.locator('body')).to_have_attribute('data-job-read', 'true')
    expect(page.get_by_role('heading', name='Settings', exact=True)).to_be_visible()
    expect(page.get_by_label('Model', exact=True)).to_have_value('synthetic-unsaved-model')
