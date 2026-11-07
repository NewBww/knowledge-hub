# Backend contract and extension handoff (historical 0.2.0)

The project-scoped routes, schema/migration observations, external-agent-only limits and update-status limitations below describe the historical 0.2.0 handoff, not the current 0.3.0 API. Current source uses a shared Warehouse, optional bounded Curator connections and manual native Sparkle integration. See [README](../../README.md), [Curator connections](../../docs/curator-connections.md), [acceptance gates](../../docs/next-version-acceptance.md) and [releasing](../../docs/releasing.md). Historical totals and packaged observations are not current verification.

**0.2.0 integration:** `create_app` now registers Library, local capture/access and human-only update-status routes. MCP also exposes external-agent intake and bounded Library projections; see `docs/mcp-first-release.md`, `docs/curator-contract.md` and `docs/library-contract.md` for the additions. Human approval remains unchanged. Update hosting is unconfigured and verified download/install is not implemented.

## Entry points and installation ownership

- Console entry point: `knowledge-hub = knowledge_hub.cli:main`.
- Default and `desktop` lazily import `knowledge_hub.desktop.launch(data_dir=...)`. They do not open a browser.
- Standalone source environment: `uv run knowledge-hub mcp --data-dir <private-data-directory>`.
- Installed console executable: `knowledge-hub mcp` (uses that installation's normal app-data directory).
- A frozen executable targeting `knowledge_hub.cli:main` accepts the same argument array: `mcp --data-dir <private-data-directory>`. Configure an MCP client with the executable path as `command` and these separate `args`; no shell command construction is required. Packaging owns the actual binary filename.
- No Hermes imports, profiles, credentials, client registration, model calls, shell tools, SQL tools, external publication or private content imports.
- Data resolution: explicit `--data-dir`, then `KNOWLEDGE_HUB_DATA_DIR`, then `platformdirs.user_data_dir('Knowledge Hub', appauthor=False)`.
- `knowledge_hub.cli.resolve_data_dir(data_dir: Path | None)` and `knowledge_hub.cli.load_agent_token(data_dir: Path)` are public helpers. The latter creates/reuses `agent.token`, mode 0600, refuses symlinks, and never opens a database. Human secrets are supplied per desktop launch and not persisted by the backend.
- Development server: `knowledge-hub serve --data-dir <private-data-directory> --port 8765`; binds only 127.0.0.1. Optional `KNOWLEDGE_HUB_HUMAN_TOKEN` is a development bootstrap secret; without it a fresh unprinted secret is generated. The desktop uses `create_app` directly, not this development override.

## HTTP

`knowledge_hub.http.create_app(data_dir: Path, human_token: str, agent_token: str) -> FastAPI` implements the originally delegated endpoint paths and JSON keys. `GET /api/health` is unauthenticated and returns `{status,version}`. No documentation/openapi endpoints are exposed publicly.

Human bootstrap: `POST /api/session` with human Bearer secret yields `{status:'authenticated'}` plus HttpOnly SameSite=strict `kh_session` cookie scoped to `/api`. Visiting `/` does not authenticate. Human Bearer alone cannot approve. Agent Bearer plus even a valid human cookie is treated as agent, not approver. Rejection is human-cookie-only too.

Host must be localhost, 127.0.0.1, ::1 or testserver. State-changing Origin, when supplied, must equal the exact request scheme/Host including port. Foreign/null origins and cross-site Fetch Metadata are rejected. No wildcard CORS. Reader assets are served from package `web/`; `/assets` serves that directory without exposing the data directory. Reader responses have CSP, no-referrer, nosniff and no-store headers.

Domain errors use `{error: code}`, with 404 for absent scoped records, 409 for stale revisions/idempotency conflicts/not-pending changes, 422 for invalid references. Pydantic validation failures use FastAPI's standard 422 envelope. Successful create/propose/review returns 200.

## Current canonical behavior / deliberate clarifications

- Proposal writes pending structured change data only. It never writes current items or increments project revision.
- Item IDs are generated UUIDs for omitted `id`; supplied IDs must name existing same-project items. Dependencies must already exist in that project. New records cannot reference other not-yet-created records in the same initial proposal; create them in a prior reviewed revision.
- Body is inert plain text. Evidence is normalized `{kind,locator,label}`; no raw-message archive is created.
- Each approval serializes with `BEGIN IMMEDIATE`, checks base revision, writes items, FTS updates, registered transitive invalidation and change status in the same transaction. Repeating an already-approved change returns its result without incrementing revision.
- Idempotency key is project-scoped. Same normalized request returns the stored change (including after acceptance); different request with the same key is rejected.
- Preview `impact.affected_ids` and `review_required_ids` are sorted stable-ID lists. Cycles terminate. Updated items normally become current, but invalid supporting dependencies keep an updated dependent `needs_review`; this is an intentional safety clarification rather than silently marking it current.
- `kind='question'` becomes `unresolved` on approval. `superseded` is a recognized read/context state, but no supersession mutation is exposed in this upsert-only slice.
- `context` currently returns `{project, revision, current, needs_review, unresolved, superseded}` with deterministic title/ID ordering from a single read transaction.
- Search uses a parameterized escaped literal FTS5 phrase, not raw user MATCH syntax. NUL-containing queries produce an explicit empty result rather than truncated SQL text. Runtime without FTS5 fails startup with an actionable error.
- `Store.backup(new_path)` uses SQLite's backup API, refuses an existing target, and writes mode 0600. Restore by opening an isolated data directory containing the backed-up `knowledge.sqlite3`. There is no remotely callable backup/file-path tool.
- Schema version 2 initializes empty; v1 databases are migrated with a pre-alteration local backup. Future schemas are refused. A genuine 0.1.0 frozen database with accepted synthetic knowledge was opened by the 0.2.0 frozen app and verified preserved with its v1 backup. No downgrade guarantee is claimed.

## MCP

Official SDK `FastMCP` stdio server from `knowledge_hub.mcp.create_mcp(data_dir)` exposes:

- `capabilities_get()`
- `project_list()`
- `project_create(name, purpose='')`
- `knowledge_search(project_id, q='', state='', max_chars=8000, cursor='')`
- `knowledge_get(project_id, item_id, max_chars=8000, body_offset=0, expected_revision=None)`
- `context_get(project_id, q='', item_ids=None, max_chars=8000, cursor='')`
- `change_propose(project_id, proposal)` — typed strict Proposal matching the HTTP body
- `change_preview(project_id, change_id)`
- `change_apply(project_id, change_id)` — always `{error:'approval_required'}`, no mutation

Discovery contains actual JSON input schemas and output schemas for structured tools; the three retrieval selectors intentionally use text-only JSON results without output schemas to avoid duplicate representations. Public SDK hooks make top-level inputs reject additional properties before SDK coercion; nested command models use `extra='forbid'`. Validation failures are protocol tool errors with generic text, not raw data/log dumps. Missing records return tool errors with stable domain codes. Stdout is protocol-only.

`capabilities_get` includes application version, `api_version:'1'`, `schema_version:2`, proposer role, human HTTP session approval boundary, client neutrality, per-installation scope, supported features and explicit unsupported features. Local stdio launch is the authorization boundary for read/propose. These are interface permissions, not an OS sandbox against a process already able to edit user-owned files.

## Implemented progressive retrieval subset

Shared `knowledge_hub.retrieval.Retrieval` supplies compact bounded agent HTTP and MCP projections. Existing `/api/projects/{id}/knowledge`, item detail and `/context` routes retain their full reader shapes and are not budgeted. Agent routes are `GET /api/projects/{id}/agent/search`, `/agent/context`, `/agent/knowledge/{item_id}` with the same existing authentication policy. Exact parameters, output fields, omissions and limitations are specified in `docs/agent-retrieval-implementation.md`.

The three MCP retrieval tools return one compact JSON TextContent with `structured_output=False`, no duplicate structured representation/output schema. Other tools retain existing output forms. `max_chars` defaults to 8000, range 1024–32000, unit serialized JSON Unicode characters (not tokens/UTF-8 bytes). Shared selection conservatively includes escaped MCP text-envelope size plus a 200-character ordinary framing allowance; arbitrary enormous correlation IDs/client rendering are not covered. Invalid/insufficient budgets fail explicitly.

Search/context pages retain `items,total`, add included counts, snapshot revision, `has_more`, selector/project/revision/projection-bound `next_cursor` and omissions. Cursors reject stale/mismatched use. Search uses lexical phrase eligibility, stable title/ID order, short explicitly partial snippets. Context selects query OR IDs, includes registered cycle-safe prerequisites and connected review/unresolved states, excludes unrelated uncertainty, deduplicates IDs, and bounds orientation metadata. No-selector context seeds five items rather than dumping all records; graph expansion and pagination are explicit. Oversized records advance as metadata-partial ID stubs; identifiers are never silently split. Explicit details traverse body fragments with Unicode character offsets and optional project-revision pinning.

Capabilities advertise `budgeted_agent_retrieval` and actual limits. Guarantee scope is only the three retrieval tools/new agent endpoints: project lists, proposals/previews and legacy reader responses are not budgeted. No semantic ranking, bounded evidence/history detail operation, delta retrieval, model integration, or constant-memory selection guarantee is claimed. Evidence counts and record IDs are lazy summaries; full sources/history are omitted. Real loopback HTTP and three actual initialized MCP subprocess scenarios verify size/schema, selector/cursor equivalence and large-body continuation; 120-record synthetic projects verify bounded defaults and complete fixed-revision pagination.

## Safe extension workflow

1. Add a failing shared behavior regression in unit/integration tests before changing canonical models/store.
2. Add HTTP and real subprocess MCP contract coverage for every exposed operation; keep both adapters on the same core service.
3. Keep the agent surface read/propose-only. A new tool must never accept approval flags, SQL, shell text, arbitrary file paths or an implicit provider dependency.
4. Add explicit schema migration/version handling and backup/restart tests before changing persistence.
5. Keep fixtures synthetic and all databases under `tmp_path`; run with TMPDIR set to the agent scratch directory.
6. Treat optional ingestion, publication, plugin runtime and model integration as separately reviewed later capabilities, not claimed placeholders.
