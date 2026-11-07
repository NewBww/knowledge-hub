"""Register reader/proposal routes on the existing authenticated application."""
from fastapi import Request
from .core import DomainError
from .library import Library
from .library_models import LibraryProposal


def register(app, store):
    library = Library(store)

    @app.get('/api/projects/{project_id}/books')
    def books(project_id: str):
        return {'books': library.books(project_id)}

    @app.get('/api/projects/{project_id}/books/{book_id}')
    def book(project_id: str, book_id: str):
        return library.book(project_id, book_id)

    @app.get('/api/projects/{project_id}/pages/{page_id}')
    def page(project_id: str, page_id: str):
        return library.page(project_id, page_id)

    @app.get('/api/projects/{project_id}/library/changes')
    def changes(project_id: str):
        return {'changes': library.changes(project_id)}

    @app.post('/api/projects/{project_id}/library/changes')
    def propose(project_id: str, command: LibraryProposal):
        return library.propose(project_id, command)

    @app.post('/api/projects/{project_id}/library/changes/{change_id}/approve')
    def approve(project_id: str, change_id: str, request: Request):
        if not getattr(request.state, 'human', False):
            raise DomainError('approval_required', 403)
        return library.approve(project_id, change_id)

    @app.post('/api/projects/{project_id}/library/changes/{change_id}/reject')
    def reject(project_id: str, change_id: str, request: Request):
        if not getattr(request.state, 'human', False):
            raise DomainError('approval_required', 403)
        return library.reject(project_id, change_id)
