# Architecture and integration

## Runtime

A dedicated macOS pywebview/WebKit window hosts local HTML/CSS/JavaScript served by FastAPI on an ephemeral IPv4 loopback port. Python application services and one SQLite store own canonical knowledge and revisions. The desktop session and agent bearer identity have different authority. The app is not a LAN multi-user server.

`core.py` defines commands/errors; `store.py` owns canonical transactions, revisions and dependency invalidation; `shared.py` provides the shared Warehouse; `library.py` owns reading surfaces; `intake.py` handles transient captures; `curator.py` handles claim/proposal workflows. HTTP and MCP adapt these services rather than duplicating business logic. Connections and bounded inference are separate from accepted knowledge.

## MCP: preferred agent boundary

Use the [bootstrap guide](agent-bootstrap.md) for installation and configuration. Discover `capabilities_get`, `warehouse_state`, setup resources and tool input schemas before use. `knowledge_search`, `context_get` and `knowledge_get` support progressive revision-bound retrieval, explicit coverage and omissions; the default budget is 8,000 serialized JSON characters, **not tokens** and not universal across tools. Follow continuation/cursor metadata; stale revisions require a fresh read.

Agents can inspect and propose. They cannot authenticate, grant access, enable processing or approve their own changes. Unknown/extra arguments are rejected. Source and model text are untrusted data, never privileged instructions. No arbitrary shell, SQL or unrestricted filesystem tools are exposed. See [retrieval](agent-retrieval.md) and [Curator contract](curator-contract.md).

## HTTP

The desktop uses authenticated project-free routes including `/api/workspace`, `/api/warehouse`, `/api/changes`, `/api/library/books` and `/api/agent/search`. Human approval routes require the human session; a bearer token does not supply that authority. Host/Origin checks and session bootstrap remain part of the boundary. Legacy `/api/projects` routes return 410 rather than selecting partitions. Do not implement a new client by relying on historical project-scoped contracts.

The exact implemented method/payload/error behavior is in [shared routes](../src/knowledge_hub/shared_http.py), [authentication](../src/knowledge_hub/http.py), [connection routes](../src/knowledge_hub/connections_http.py), [MCP tools](../src/knowledge_hub/mcp.py) and contract tests. These routes are local integration surfaces, not permission to publish a remote API. Do not scrape human HTML when a semantic MCP tool is available.

## Extension rules

Add typed, reviewed adapters, explicit capabilities, bounded input/output and failure states. Keep secrets in appropriate credential stores, not knowledge. Preserve idempotency, revision checks, evidence locators and human-only decisions. A new provider requires tested model/tool/account isolation; a listed preset alone does not establish support. No runtime arbitrary-plugin loader exists.

## Scoped sources and durable jobs

`context_sources.py` owns persistent read-only grants, exclusion/ignore checks and bounded text listing/read/search; `native_picker.py` is the trusted desktop-only mixed selection bridge. HTTP cannot mint grants from paths. `context_sources_http.py` and `curator_jobs_http.py` require human sessions, not agent bearer authority; they are not new MCP filesystem tools.

`curator_jobs.py` persists jobs separately in `curator-jobs.sqlite3`, pins source generation/digests, fences worker leases and saves prepared proposal checkpoints. Idempotent proposal replay plus exact readback bridges the job journal and canonical proposal store; it never approves a change. Connection policy and sources are revalidated before publication. The application host owns the foreground worker lifecycle: stop on Quit, recover on reopen. No independent background service or arbitrary polling connector exists.

Cross-book follow-up/outbox orchestration is incomplete. Source integration tests do not substitute for native picker/window or installed updater acceptance. See [documentation status](documentation.md) and [Contributing](../CONTRIBUTING.md).
