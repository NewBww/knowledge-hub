"""Local reader request anchors, never instructions or Warehouse ownership."""


def capture_context(store, project_id, context):
    """Freeze an optional passage in the capture's integrity-protected snapshot."""
    if context is None:
        return {}
    from .core import DomainError
    from .library import Library
    from .shared import SharedWarehouse

    scope = SharedWarehouse(store).scope()
    if project_id != scope:
        raise DomainError('invalid_request_context', 422)
    try:
        page = Library(store).page(scope, context.page_id)
    except DomainError as error:
        if error.code == 'page_not_found':
            raise DomainError('invalid_request_context', 422) from None
        raise
    if page['revision'] != context.page_revision:
        raise DomainError('request_context_stale')
    sections = [section for section in page['sections']
                if context.section_id is None or section['id'] == context.section_id]
    if not any(context.passage.strip() and context.passage in section['body'] for section in sections):
        raise DomainError('invalid_request_context', 422)
    return {'request_context': context.model_dump(mode='json', exclude_none=True)}
