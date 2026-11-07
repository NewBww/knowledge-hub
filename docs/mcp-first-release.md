# MCP Library and external-agent intake — 0.2.0

The installed executable supports `mcp` directly. Discover its schemas; no harness/provider keys or connector setup belongs in Knowledge Hub. Capabilities report app version 0.2.0, API version 1 and SQLite schema version 2. Human approval remains outside agent authority.

## Two ingestion routes

- Agent already has supported knowledge: use existing `change_propose(project_id, proposal)`. No capture or capture-access permission is required. Search/reuse existing canonical facts first; submit evidence and explicit uncertainty, not an entire conversation archive.
- Human captured material in the app: the human enables project capture access, the agent lists/selects source slices, claims the inspected snapshot and submits a curation result. Access covers that project's queued/future captures until revoked; it is not proof of a connected harness or safe downstream model policy.

## Capture tools

- `capture_list(project_id, limit=20, offset=0)`: metadata only, limit 1–100, follow `next_offset`.
- `capture_get(project_id, capture_id, source_id='paste', offset=0, max_chars=4000, attachment_id=null, byte_offset=0, max_bytes=16384)`: one selected inert text slice; source may be paste or file ID. Original attachment bytes require explicit attachment ID and return base64 chunks. Max text slice 20,000 characters, max raw attachment slice 1 MiB. These are field limits, not total wire-character guarantees.
- `capture_claim(project_id, capture_id, claimant, snapshot_sha256, base_revision, ttl_seconds=300)`: exclusive expiring lease of an inspected snapshot at the current project revision.
- `curation_submit(project_id, capture_id, submission)`: strict model from `docs/curator-contract.md`, including claim token/snapshot/base revision, summary, Warehouse upserts and optional typed Library suggestions. Persists a pending Warehouse change and suggestions; it never accepts facts or publishes pages. Exact retry is idempotent.

No agent tools enable capture access, delete captures, execute models/commands, configure providers or grant approval. Revocation is checked on subsequent capture calls. Data-root advisory locking coordinates HTTP and distinct stdio processes. Exact submission recovery is tested across process death between database commit and result-manifest save.

## Library tools

- `library_list(project_id, limit=20, offset=0)`: up to 20 book metadata entries, no prose or page-ID dump.
- `library_get(project_id, book_id, limit=20, offset=0, expected_revision=null)`: book metadata with up to 20 ordered page summaries, no full page prose. Purpose/overview are intentionally omitted. Pin the book revision during pagination; this is not a project-wide semantic snapshot guarantee.
- `library_page_get(project_id, page_id, section_index=0, body_offset=0, max_chars=4000, support_offset=0, link_offset=0, expected_revision=null)`: one body fragment (1–20,000 characters), at most 20 support references and 20 links. Follow the explicit section/body/support/link continuations. Pin page revision during traversal. Limits constrain individual fields/counts, not a fixed total JSON budget; source freshness can change independently of prose revision.
- `library_propose(project_id, proposal)`: typed pending Library-only change. Warehouse facts must first be human-approved; then cite their actual canonical IDs/revisions in proposed factual sections. See `docs/library-contract.md` for exact payloads.

Capture retrieval/submission and Library tools use single compact JSON TextContent without redundant structured copies, except the small claim receipt. Existing Warehouse search/context/detail retain their separately tested whole-response character-budget contract. Project lists, large proposal writes/previews and mutation receipts do not inherit that guarantee.

## Reviewed workflow

1. Read/reconcile canonical knowledge through bounded Warehouse tools.
2. Submit new/updated facts as pending changes, directly or from claimed capture.
3. Human accepts/rejects in the app. Wait/read current revisions; an agent cannot bypass this step.
4. Propose a Library page/book using accepted canonical support. Human reviews/publishes separately; do not duplicate facts into a second truth master.
5. The UI offers arrangement of captured Library suggestions, preserving source work until final Library review or explicit dismissal. Raw captures are removed on finish unless the human deliberately retains them until expiry.

This document records the historical first-release contract. The current project-free interface and versioned setup resource are specified in [agent bootstrap](agent-bootstrap.md) and the [Curator contract](curator-contract.md). Schema-3 discovery and real SDK subprocess tests verify the current bounded setup/retrieval boundary; packaged acceptance remains a separate gate. Neither synthetic test success nor connection discovery certifies a particular account, external harness or provider privacy policy.
