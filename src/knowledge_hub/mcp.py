"""Official MCP Python SDK stdio adapter; agent-only capabilities."""
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from jsonschema import Draft202012Validator
from .store import Store
from .retrieval import Retrieval, compact, DEFAULT_CHARS, MIN_CHARS, MAX_CHARS
from mcp.types import TextContent
from .core import Proposal, DomainError
from .curator import Curator, CurationSubmission
from .library import Library
from .library_models import LibraryProposal
from .version import VERSION
from .shared import public



class StrictMCP(FastMCP):
    """Use public SDK hooks to reject extra fields before FastMCP coercion."""

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            properties = tool.inputSchema.get('properties', {})
            if 'project_id' in properties:
                properties = {**properties, 'project_id': {**properties['project_id'],
                    'deprecated': True, 'description': 'Deprecated and ignored; never selects a partition or grants access.'}}
            tool.inputSchema = {**tool.inputSchema, 'properties': properties, 'additionalProperties': False}
        return tools

    async def call_tool(self, name, arguments):
        tool = next((tool for tool in await self.list_tools() if tool.name == name), None)
        if tool is None:
            raise ToolError('unknown_tool')
        if not Draft202012Validator(tool.inputSchema).is_valid(arguments):
            raise ToolError('invalid_arguments')
        try:
            return await super().call_tool(name, arguments)
        except ToolError as error:
            if isinstance(error.__cause__, DomainError):
                raise ToolError(error.__cause__.code) from None
            raise ToolError('invalid_arguments') from None


def create_mcp(data_dir: Path) -> FastMCP:
    store = Store(data_dir)
    server = StrictMCP('Knowledge Hub', instructions='One shared local Warehouse; no project setup required. Read knowledgehub://setup or setup_guide_get before setup. Human review is required to apply changes. Optional project_id arguments are deprecated compatibility fields and never select a partition or grant access.', log_level='CRITICAL')

    def warehouse():
        from .shared import SharedWarehouse
        return SharedWarehouse(store)

    def scope():
        return warehouse().scope()

    @server.tool()
    def capabilities_get() -> dict[str, Any]:
        """Discover version, local scope and approval policy."""
        unsupported = ['llm_bridge', 'external_publication', 'private_import',
                       'plugin_runtime', 'arbitrary_shell', 'arbitrary_sql', 'remote_mcp', 'multi_user']
        return {'version': VERSION, 'api_version': '1', 'schema_version': 3,
                'approval_required': True, 'approval_boundary': 'human_http_session_only',
                'transport': 'stdio', 'fts5': store.fts_available, 'role': 'proposer',
                'client_neutral': True, 'data_scope': 'per_installation_local_directory',
                'setup_guide_uri': 'knowledgehub://setup', 'setup_guide_version': '1',
                'project_selection_required': False,
                'supported_features': ['shared_warehouse', 'agent_bootstrap_v1', 'plain_text_knowledge', 'literal_fts_search',
                    'reviewed_changes', 'registered_dependency_invalidation', 'optimistic_concurrency',
                    'idempotency', 'evidence', 'revision_context', 'sqlite_backup', 'budgeted_agent_retrieval',
                    'library_books_pages', 'local_capture_queue', 'external_agent_curation'],
                'retrieval_limits': {'unit': 'json_characters', 'default': DEFAULT_CHARS, 'min': MIN_CHARS,
                    'max': MAX_CHARS, 'scope': 'knowledge_search,context_get,knowledge_get_only',
                    'token_count': False, 'projection': 'compact-v1'},
                'unsupported_features': unsupported, 'excluded': unsupported}

    @server.tool()
    def project_list() -> dict[str, Any]:
        """Deprecated compatibility discovery. No selectable projects; use warehouse_state."""
        return {'projects': [], 'deprecated': True, 'replacement': 'warehouse_state'}

    @server.tool()
    def warehouse_state() -> dict[str, Any]:
        """Read shared revision, knowledge/review/book counts and migration status; no scope selection."""
        return warehouse().state()

    @server.tool(structured_output=False)
    def knowledge_search(q: str = '', state: str = '', max_chars: int = DEFAULT_CHARS, cursor: str = '', project_id: str | None = None) -> list[TextContent]:
        """Find compact snippets; max_chars bounds JSON characters, not tokens. Follow next_cursor."""
        return [TextContent(type='text', text=compact(public(Retrieval(store).search(scope(), q, state, max_chars, cursor))))]

    @server.tool(structured_output=False)
    def knowledge_get(item_id: str, max_chars: int = DEFAULT_CHARS, body_offset: int = 0, expected_revision: int | None = None, project_id: str | None = None) -> list[TextContent]:
        """Inspect an explicit body fragment. Follow next_body_offset and pin expected_revision to avoid mixing revisions."""
        return [TextContent(type='text', text=compact(public(Retrieval(store).get(scope(), item_id, max_chars, body_offset, expected_revision))))]

    @server.tool(structured_output=False)
    def context_get(q: str = '', item_ids: list[str] | None = None, max_chars: int = DEFAULT_CHARS, cursor: str = '', project_id: str | None = None) -> list[TextContent]:
        """Select query OR IDs with registered prerequisites and uncertainty. No selector gives orientation only."""
        return [TextContent(type='text', text=compact(public(Retrieval(store).context(scope(), q, item_ids, max_chars, cursor))))]

    @server.tool(structured_output=False)
    def capture_list(limit: int = 20, offset: int = 0, project_id: str | None = None) -> list[TextContent]:
        """List capture metadata only after human-enabled shared access; follow next_offset."""
        return [TextContent(type='text', text=compact(Curator(store).capture_list(scope(), limit, offset)))]

    @server.tool(structured_output=False)
    def capture_get(capture_id: str, source_id: str = 'paste', offset: int = 0,
                    max_chars: int = 4000, attachment_id: str | None = None,
                    byte_offset: int = 0, max_bytes: int = 16384, project_id: str | None = None) -> list[TextContent]:
        """Read one inert source slice. Original bytes require explicit attachment_id; follow offsets.

        Human-enabled access is required. Text is limited to 20,000 characters, attachment
        chunks to 1 MiB raw bytes; these are not total JSON/wire-size budgets.
        """
        return [TextContent(type='text', text=compact(Curator(store).capture_get(
            scope(), capture_id, source_id, offset, max_chars, attachment_id, byte_offset, max_bytes)))]

    @server.tool()
    def capture_claim(capture_id: str, claimant: str, snapshot_sha256: str,
                      base_revision: int, ttl_seconds: int = 300, project_id: str | None = None) -> dict[str, Any]:
        """Lease an inspected capture snapshot at the shared revision; never approves."""
        return Curator(store).claim(scope(), capture_id, claimant, snapshot_sha256, base_revision, ttl_seconds)

    @server.tool(structured_output=False)
    def curation_submit(capture_id: str, submission: CurationSubmission, project_id: str | None = None) -> list[TextContent]:
        """Persist pending Warehouse proposal and typed Library suggestions from a live claim.

        Suggestions are not published Library entities. All agent output requires human review.
        """
        return [TextContent(type='text', text=compact(Curator(store).curation_submit(scope(), capture_id, submission)))]

    def page_window(values, offset, limit):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20:
            raise DomainError('invalid_retrieval_limit', 422)
        end = min(offset + limit, len(values))
        return values[offset:end], end if end < len(values) else None

    def book_metadata(book):
        return {key: book[key] for key in ('id', 'title', 'revision', 'state', 'support_state', 'page_count')}

    @server.tool(structured_output=False)
    def library_list(limit: int = 20, offset: int = 0, project_id: str | None = None) -> list[TextContent]:
        """List bounded book metadata, never page IDs/prose. Limit 1–20; follow next_offset."""
        books = Library(store).books(scope())
        selected, next_offset = page_window(books, offset, limit)
        result = {'books': [book_metadata(book) for book in selected], 'total': len(books), 'next_offset': next_offset}
        return [TextContent(type='text', text=compact(result))]

    def page_metadata(page):
        return {key: page[key] for key in ('id', 'title', 'revision', 'state', 'support_state')}

    @server.tool(structured_output=False)
    def library_get(book_id: str, limit: int = 20, offset: int = 0,
                    expected_revision: int | None = None, project_id: str | None = None) -> list[TextContent]:
        """Read book metadata and 1–20 ordered page summaries. No prose; use library_page_get.

        Pin expected_revision while paging. Purpose/overview are omitted from this projection.
        """
        book = Library(store).book(scope(), book_id)
        if expected_revision is not None and expected_revision != book['revision']:
            raise DomainError('stale_revision')
        pages, next_offset = page_window(book['pages'], offset, limit)
        result = {**book_metadata(book), 'pages': [page_metadata(page) for page in pages],
                  'offset': offset, 'next_offset': next_offset}
        return [TextContent(type='text', text=compact(result))]

    @server.tool(structured_output=False)
    def library_page_get(page_id: str, section_index: int = 0,
                         body_offset: int = 0, max_chars: int = 4000, support_offset: int = 0,
                         link_offset: int = 0, expected_revision: int | None = None, project_id: str | None = None) -> list[TextContent]:
        """Read one explicit page section fragment, at most 20 support references and 20 links.

        Follow next_section_index, next_body_offset, next_support_offset and next_link_offset.
        Pin expected_revision across fragments. max_chars 1–20,000 bounds body only, not JSON.
        """
        if not 1 <= max_chars <= 20000 or body_offset < 0 or section_index < 0:
            raise DomainError('invalid_retrieval_limit', 422)
        page = Library(store).page(scope(), page_id)
        if expected_revision is not None and expected_revision != page['revision']:
            raise DomainError('stale_revision')
        if section_index >= len(page['sections']):
            raise DomainError('section_not_found', 404)
        section = page['sections'][section_index]
        supports, next_support_offset = page_window(section['supports'], support_offset, 20)
        links, next_link_offset = page_window(page['links'], link_offset, 20)
        body = section['body'][body_offset:body_offset + max_chars]
        end = body_offset + len(body)
        result = {**page_metadata(page), 'section_count': len(page['sections']), 'section_index': section_index,
                  'next_section_index': section_index + 1 if section_index + 1 < len(page['sections']) else None,
                  'section': {key: section[key] for key in ('id', 'kind', 'support_state')},
                  'body_offset': body_offset, 'total_chars': len(section['body']),
                  'next_body_offset': end if end < len(section['body']) else None,
                  'support_offset': support_offset, 'support_count': len(section['supports']),
                  'next_support_offset': next_support_offset, 'links': links, 'link_count': len(page['links']),
                  'link_offset': link_offset, 'next_link_offset': next_link_offset}
        result['section'].update(body=body, supports=supports)
        return [TextContent(type='text', text=compact(result))]

    @server.tool(structured_output=False)
    def library_propose(proposal: LibraryProposal, project_id: str | None = None) -> list[TextContent]:
        """Persist a pending Library-only proposal; no publication or Warehouse writes."""
        return [TextContent(type='text', text=compact(Library(store).propose(scope(), proposal)))]

    @server.tool()
    def change_propose(proposal: Proposal, project_id: str | None = None) -> dict[str, Any]:
        """Persist a validated idempotent proposal and impact preview, without applying it."""
        return store.propose(scope(), proposal)

    @server.tool()
    def change_preview(change_id: str, project_id: str | None = None) -> dict[str, Any]:
        """Read a stored proposal and its registered dependency impact."""
        shared_scope = scope()
        with store.connect() as db:
            return store._change(db, shared_scope, change_id)

    @server.tool()
    def change_apply(change_id: str, project_id: str | None = None) -> dict[str, Any]:
        """Refuse agent application. A human must approve using the desktop review session."""
        return {'error': 'approval_required'}

    from .setup_mcp import register_setup
    register_setup(server, store)
    return server
