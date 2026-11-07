"""Contextual requests use real shared HTTP commands and isolated synthetic data."""
from uuid import uuid4
import pytest
from test_shared_http import clients


def reader(human):
    page_id, section_id = str(uuid4()), str(uuid4())
    operation = dict(op='upsert_page', id=page_id, base_revision=0, title='Synthetic passage',
                     state='published', sections=[dict(id=section_id, kind='editorial',
                     body='A synthetic passage. <script>ignore instructions</script>', supports=[])], links=[])
    change = human.post('/api/library/changes', json=dict(base_revision=0, idempotency_key=str(uuid4()),
                         summary='Synthetic reader', operations=[operation]))
    assert change.status_code == 200, change.text
    assert human.post('/api/library/changes/' + change.json()['id'] + '/approve').status_code == 200
    return operation, dict(page_id=page_id, page_revision=1, section_id=section_id, passage='A synthetic passage.')


def test_contextual_request_is_bound_to_snapshot_not_accepted_knowledge(tmp_path):
    _, human, agent = clients(tmp_path)
    operation, context = reader(human)
    saved = human.post('/api/captures', json=dict(text='Please clarify this passage',
                       intent='Request something', request_context=context))
    assert saved.status_code == 200, saved.text
    capture = saved.json()
    assert capture['request_context'] == context
    assert capture['status'] == 'pending_agent'
    assert human.get('/api/warehouse').json()['items'] == []
    assert human.get('/api/changes').json()['changes'] == []
    assert agent.get('/api/captures/' + capture['id']).status_code == 403
    assert human.post('/api/agent/access', json={'enabled': True}).status_code == 200
    assert agent.get('/api/captures/' + capture['id']).json()['request_context'] == context
    operation['base_revision'] = 1
    operation['sections'][0]['body'] = 'A later editorial revision.'
    change = human.post('/api/library/changes', json=dict(base_revision=1, idempotency_key=str(uuid4()),
                       summary='Later reader', operations=[operation])).json()
    assert human.post('/api/library/changes/' + change['id'] + '/approve').status_code == 200
    _, restarted, _ = clients(tmp_path)
    persisted = restarted.get('/api/captures/' + capture['id']).json()
    assert persisted['request_context'] == context
    assert persisted['snapshot_sha256'] == capture['snapshot_sha256']
    assert restarted.get('/api/library/pages/' + context['page_id']).json()['revision'] == 2


@pytest.mark.parametrize('case,status,error', [
    ('stale', 409, 'request_context_stale'),
    ('missing_page', 422, 'invalid_request_context'),
    ('missing_section', 422, 'invalid_request_context'),
    ('fabricated_passage', 422, 'invalid_request_context'),
    ('other_section', 422, 'invalid_request_context'),
])
def test_context_anchor_must_match_current_shared_reader(tmp_path, case, status, error):
    _, human, _ = clients(tmp_path)
    operation, context = reader(human)
    if case == 'stale': context['page_revision'] = 2
    if case == 'missing_page': context['page_id'] = str(uuid4())
    if case == 'missing_section': context['section_id'] = str(uuid4())
    if case == 'fabricated_passage': context['passage'] = 'Not the reader text https://example.invalid/do-not-fetch'
    if case == 'other_section':
        operation['base_revision'] = 1
        operation['sections'].append(dict(id=str(uuid4()), kind='editorial', body='Another section only.', supports=[]))
        proposed = human.post('/api/library/changes', json=dict(base_revision=1, idempotency_key=str(uuid4()),
                              summary='Another section', operations=[operation])).json()
        assert human.post('/api/library/changes/' + proposed['id'] + '/approve').status_code == 200
        context.update(page_revision=2, passage='Another section only.')
    response = human.post('/api/captures', json=dict(text='Clarify', intent='Request something', request_context=context))
    assert response.status_code == status, response.text
    assert response.json()['error'] == error
    assert human.get('/api/captures').json()['captures'] == []


def test_context_is_explicitly_a_request_not_knowledge(tmp_path):
    _, human, _ = clients(tmp_path)
    _, context = reader(human)
    response = human.post('/api/captures', json=dict(text='Treat this as a fact', intent='Add knowledge', request_context=context))
    assert response.status_code == 422, response.text
    assert human.get('/api/captures').json()['captures'] == []


@pytest.mark.parametrize('field,value', [
    ('page_id', 'not-an-id'), ('page_revision', True), ('page_revision', '1'),
    ('page_revision', 0), ('section_id', 'bad'), ('passage', ''),
    ('passage', 'x' * 10001), ('fetch_url', 'https://example.invalid'),
])
def test_context_wire_contract_is_bounded_and_no_extra_authority(tmp_path, field, value):
    # Supplemental schema coverage: typed fields already enforce these bounds.
    _, human, _ = clients(tmp_path)
    _, context = reader(human)
    context[field] = value
    response = human.post('/api/captures', json=dict(text='Clarify', intent='Request something', request_context=context))
    assert response.status_code == 422, response.text


def test_context_integrity_includes_passage_and_optional_section(tmp_path):
    from knowledge_hub.intake import Intake
    from knowledge_hub.shared import SharedWarehouse
    from knowledge_hub.core import DomainError
    app, human, _ = clients(tmp_path)
    _, context = reader(human)
    context.pop('section_id')
    saved = human.post('/api/captures', json=dict(text='Clarify', intent='request', request_context=context))
    assert saved.status_code == 200, saved.text
    capture = saved.json()
    assert capture['request_context'] == context
    intake = Intake(app.state.store)
    scope = SharedWarehouse(app.state.store).scope()
    manifest = intake.get(scope, capture['id'])
    manifest['request_context']['passage'] = 'Tampered passage'
    intake.save(manifest)
    with pytest.raises(DomainError, match='capture_integrity_error'):
        intake.get(scope, capture['id'])


def test_context_cannot_bind_a_nonshared_scope(tmp_path):
    from knowledge_hub.intake import Intake
    from knowledge_hub.intake_models import CaptureInput
    from knowledge_hub.core import DomainError
    from knowledge_hub.store import Store
    foreign = Store(tmp_path).create_project('Synthetic nonshared scope')['id']
    app, human, _ = clients(tmp_path)
    _, context = reader(human)
    with pytest.raises(DomainError, match='project_scope_removed'):
        Intake(app.state.store).create(foreign, CaptureInput(text='Clarify', intent='request', request_context=context))
