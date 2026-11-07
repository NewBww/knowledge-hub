# Progressive agent retrieval: implemented contract

> **Historical/internal project-scoped contract:** the route table below is not the current public HTTP interface. Legacy project routes return HTTP 410 in the shared application. Use [agent bootstrap](agent-bootstrap.md), the [Curator contract](curator-contract.md), and current schema discovery; project-scoped service internals do not authorize clients to call removed routes.

The shared `knowledge_hub.retrieval.Retrieval` service implements deterministic, local, project-scoped retrieval. It uses SQLite literal FTS5 phrase eligibility and stable title/ID ordering, **not semantic ranking or RAG**. No model, tokenizer, embedding, provider or client integration is required.

## Endpoints and parameters

All new HTTP routes are authenticated by the existing agent Bearer or human-session policy. They do not grant approval permissions. Existing full reader routes (`/knowledge`, `/knowledge/{id}`, `/context`) are unchanged and are **not budgeted**.

| HTTP GET under `/api/projects/{project_id}/agent` | MCP tool | Parameters beyond project ID |
| --- | --- | --- |
| `/search` | `knowledge_search` | `q=''`, `state=''`, `max_chars=8000`, `cursor=''` |
| `/context` | `context_get` | `q=''`, `item_ids=[]`, `max_chars=8000`, `cursor=''` |
| `/knowledge/{item_id}` | `knowledge_get` | `item_id`, `max_chars=8000`, `body_offset=0`, `expected_revision=null` |

HTTP context IDs are repeated query parameters: `?item_ids=id1&item_ids=id2`. MCP takes a JSON array (or null for none). Supply a query **or** nonempty IDs; both gives `conflicting_selectors` (HTTP 422). Unknown selected IDs fail scoped lookup (404), not silently disappear. Empty IDs behave like no selector.

## Measurable budget, not token accounting

`max_chars` is an integer from **1024 through 32000**, default **8000**. It limits the actual compact serialized JSON envelope, not merely body length. `budget_unit='json_characters'` means Unicode characters in JSON serialized with `ensure_ascii=False`; JSON escaping and metadata count. This is neither UTF-8 bytes nor model-independent tokens. Newline/quote/backslash/NUL escaping is included. Body offsets count Unicode characters in the canonical text, not bytes, graphemes or escaped JSON positions.

Both adapters select the same projection. The service conservatively measures the escaped, single-text MCP tool-result envelope and reserves another 200 characters for ordinary JSON-RPC framing. HTTP JSON is consequently smaller than this limit. Real subprocess tests measure the actual SDK output line (not a reserialized parsed value). Arbitrarily long client-supplied JSON-RPC correlation IDs, transport headers, and downstream client rendering are outside the budget; a normal numeric-ID wire response is covered by the allowance.

An out-of-range budget returns `invalid_budget` (422). If the envelope or an indivisible identifier cannot fit, `budget_too_small` (422) is explicit: increase the budget. It never silently shortens an identifier. A valid small budget may still be insufficient for context metadata. No exact token estimate is advertised.

## Search and pagination

Search returns readable `{items,total,...}`. Normal entries contain `id,title,kind,state,revision,snippet,snippet_partial,detail_item_id`. Snippets are at most 160 characters, near a literal body occurrence when available; title-only/token-normalized matches may use a body prefix. They are excerpts, not claims that the entire body was returned. No full bodies, source text, evidence arrays or history are in search.

Page metadata includes `project_id`, snapshot `revision`, exact eligible `total`, this-page `included_count`, `has_more`, `next_cursor`, `projection='compact-v1'`, `max_chars`, and explicit `omissions`. Included IDs are the item IDs in the page; omitted eligible records are `total - included_count` (including earlier pages). Follow `next_cursor` until `has_more=false`; an individual page is not a completeness claim. No duplicates or omissions occur when following cursors at a fixed revision/selector.

Cursors bind the project, project revision, operation/projection and exact query/state or canonicalized ID selector. Mismatches, stale revisions, malformed cursors and invalid offsets return `invalid_cursor` (409). A caller may change the budget when continuing. Cursors are deterministic continuation hints, not authorization credentials or signed tamper-proof tokens. Every call performs scoped authorization/lookup independently.

If a single oversized entry cannot fit an otherwise empty page, the page emits an indivisible `{id,kind,state,revision,metadata_partial:true,detail_item_id}` stub and advances. It does **not** clip a title/claim and call it complete. If even that stub cannot fit, the explicit budget error applies. The selected body can be read using the detail operation below. Oversized omitted titles themselves do not currently have a separate agent metadata-range endpoint; the legacy full reader remains available explicitly.

## Context selection and uncertainty

An explicit query selects lexical phrase matches. Explicit IDs are deduplicated and validated in the project. Without either selector, orientation seeds only the first five stable title/ID records. `orientation_only=true` and `orientation_omitted_count` distinguish this from a project-wide context dump.

Selection expands to recorded transitive prerequisites and connected `needs_review`/`unresolved` dependents, including prerequisites of those warnings, to a cycle-safe fixed point. Only registered same-project edges count; unrelated unresolved records/projects and pending proposals are excluded. Entries retain their actual lifecycle state. This is a conservative graph-based relevance rule, not inference that unregistered uncertainty is absent.

Context returns the same paginated envelope plus:

- `project`: ID, name prefix (80 characters), purpose prefix (160), and explicit `name_partial`/`purpose_partial` flags.
- `matched_count`: exact seed count before graph expansion; `total`: exact expanded selected count.
- `coverage='registered_dependencies_and_connected_uncertainty_only'`.
- Compact item snippets, `body_chars`, `evidence_count`, and `detail_item_id` as a lazy reference to the canonical record. Full locators/quotes, dependency arrays, proposal/source archives and history are omitted.

If prerequisites or warnings span pages, `has_more` makes incomplete coverage visible; no page asserts a complete context pack. Connected warnings are never removed from the eligible set to make current facts appear clean. Default orientation may expand beyond five eligible records when their registered graph requires it, but serialization remains budgeted.

## Explicit body inspection

`knowledge_get` returns only the selected item's metadata and a bounded `body` fragment, `body_offset`, full `body_chars`, `next_body_offset`, `body_partial`, `project_revision`, and item `revision`. A fragment is never labelled the complete claim. `next_body_offset=null` means the end was reached, not that earlier fragments were included. Concatenating segments from offset zero recovers the full text, including Unicode, NUL and escaped characters.

Pass the first response's `project_revision` as `expected_revision` on subsequent calls to prevent mixing revisions. A mismatch returns `stale_revision` (409). Negative/beyond-end offsets return `invalid_body_offset` (422); offset exactly at the end returns an empty final fragment. Without revision pinning, independent calls can observe different snapshots; clients must not infer a pinned traversal. Oversized title metadata is explicitly omitted with `metadata_partial=true` to keep body traversal usable.

## MCP representation and scope limits

The three retrieval tools use official `FastMCP.tool(structured_output=False)` and return **one compact JSON TextContent**, no duplicated `structuredContent` and no output schema requiring it. Tool input schemas expose selectors/budgets/continuations; unknown arguments are rejected. Existing MCP consumers must parse the text JSON for these three tools. Search still preserves its readable `items`/`total` envelope. Other tools retain their existing representation.

Capabilities advertise `budgeted_agent_retrieval` and actual limits. This guarantee applies **only to these three retrieval tools and corresponding agent HTTP routes**. Project lists, proposal/create/preview results and legacy human-reader routes are not bounded by this contract. No arbitrary shell/SQL/file-path tools were added.

This is a supported subset of [the broader acceptance contract](agent-retrieval.md): evidence-reference counts and record IDs are exposed, but separate bounded evidence/history inspection, semantic ranking, deltas, source ingestion, and automatic discovery of unregistered prerequisites are not implemented. Computation is not bounded by the response budget: selection scans compact metadata and registered edges, and SQLite evaluates body slices/lengths locally. No claim is made about constant-memory/constant-time retrieval at arbitrary database scale.

## Verification

Synthetic regression projects contain 120 long Unicode bodies and long evidence locators. Tests exercise full fixed-revision search/context pagination, scope isolation, unrelated uncertainty omission, prerequisite cycles, long purpose/identifier/title handling, invalid/stale/mismatched cursors, Unicode/escaped/NUL body reconstruction, budget errors, preserved full reader shapes, real loopback HTTP, and three real MCP subprocess scenarios (wire budget/schema, selector/cursor/equivalence, and large-body traversal). The MCP SDK process handles the actual initialized JSON-RPC traffic; responses are never fabricated.
