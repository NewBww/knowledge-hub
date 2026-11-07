# Library contract (frozen integration surface)

`from knowledge_hub.library_http import register; register(app, store)` installs the routes below. Existing authentication/DomainError handler stays on the parent app. Agent credentials can read/propose; approve/reject require `request.state.human`. Canonical Warehouse APIs remain unchanged.

Python: `Library(store).books(project_id)`, `.book(project_id, book_id)`, `.page(project_id, page_id)`, `.changes(project_id)`, `.propose(project_id, LibraryProposal)`, `.approve(project_id, change_id)`, `.reject(project_id, change_id)`. Models live in `knowledge_hub.library_models`. All return JSON-compatible dicts/lists. Service approval is a trusted internal boundary, just like Store.approve; HTTP enforces human authority.

## HTTP

- GET `/api/projects/{project_id}/books` → `{"books":[{"id":"UUID","title":"Guide","purpose":"Learn","overview":"Introduction","revision":1,"state":"published","support_state":"current","page_count":1,"page_ids":["UUID"]}]}`
- GET `/api/projects/{project_id}/books/{book_id}` → same book plus `pages` in `page_ids` order (full readable page objects).
- GET `/api/projects/{project_id}/pages/{page_id}` → `{"id":"UUID","project_id":"UUID","title":"Basics","revision":1,"state":"published","support_state":"current","sections":[{"id":"UUID","kind":"factual","body":"Readable explanation","supports":[{"item_id":"UUID","revision":1,"relationship":"supports","current_revision":1,"state":"current"}],"support_state":"current"}],"links":[]}`. Links are same-project page UUIDs, not factual support. Support reads expose IDs/state/revisions, not duplicate canonical bodies; use existing `/knowledge/{id}` for evidence/full canonical detail.
- POST `/api/projects/{project_id}/library/changes` → pending change; GET same → `{"changes":[...]}`.
- POST `/api/projects/{project_id}/library/changes/{change_id}/approve` or `/reject` → resulting change; no request body. Agent attempts return 403 `approval_required`.

Example POST (replace illustrative UUIDs with stable generated UUIDs):

```json
{
  "base_revision": 1,
  "idempotency_key": "guide-v1",
  "summary": "Create reader guide using accepted knowledge",
  "operations": [
    {"op":"upsert_page","id":"11111111-1111-4111-8111-111111111111","base_revision":0,"title":"Basics","state":"published","sections":[{"id":"22222222-2222-4222-8222-222222222222","kind":"factual","body":"Readable explanation","supports":[{"item_id":"33333333-3333-4333-8333-333333333333","revision":1,"relationship":"supports"}]}],"links":[]},
    {"op":"upsert_book","id":"44444444-4444-4444-8444-444444444444","base_revision":0,"title":"Guide","purpose":"Learn","overview":"Introduction","state":"published","page_ids":["11111111-1111-4111-8111-111111111111"]}
  ]
}
```

Book/page IDs are caller-preallocated UUIDs, entity `base_revision=0` means create; updates require the current entity revision. `base_revision` at proposal root is current project revision (GET `/api/projects`). Successful approval increments project revision and each changed entity revision; it does not mutate Warehouse items. Book/page operations replace the entire entity; to refine a section, submit its whole page preserving other sections. Page and book operations may refer to entities created in the same proposal, irrespective of operation order. Books may share pages and pages/sections may reuse the same canonical item without cloning it.

Change shape: `{id,project_id,base_revision,status,summary,operations}`; approval adds `result_revision`. Status is pending/approved/rejected. Exact repeated idempotency key+request returns the original change; changed payload returns 409 `idempotency_conflict`. Approval retries are idempotent; rejection cannot reverse approval.

Publication `state` = draft/published/archived, separate from `support_state` = current/needs_review/unresolved. Factual sections require explicit support to publish; editorial sections are non-factual navigation/introduction, not an assertion loophole. Draft factual gaps remain visible as unresolved. All cited IDs must exist in the same project's Warehouse, with exact revision; published support must be current. All links/page_ids must resolve in the same project. Duplicate entity, section, support or navigation references are rejected. Unknown fields are rejected.

Both proposal and approval validate root/entity/support revisions and publication eligibility atomically. 409 `stale_revision`/`stale_support`, 422 `invalid_reference`/`unsupported_publication`, 404 `project_not_found`/`book_not_found`/`page_not_found`/`change_not_found`. A rejected/stale proposal changes no published content. New facts are staged through Store.propose/approve before library proposal: no atomic mixed canonical+library publication.

Support freshness is computed from current canonical revisions/states at read time. Existing Warehouse registered transitive dependency invalidation therefore propagates into section/page/book rollups, cycle-safely, without replacing published prose. `needs_review` identifies revision mismatch/changed or superseded support; `unresolved` identifies absent/noncurrent unresolved support. Coverage is only registered references, not semantic discovery. Human review cannot guarantee paraphrase fidelity. Book overviews are editorial, not another canonical fact database.

SQLite v1 is transactionally migrated to v2 with a local `knowledge.sqlite3.v1.bak` backup before alteration; future schemas refuse opening. Original canonical records/proposals survive. Runtime data remains under the Store's caller-selected local application-data directory; no app/repo fixtures are loaded. Full reader routes intentionally return complete selected books/pages; bounded agent contexts remain the existing Warehouse retrieval contract, not a new unbounded context endpoint.

## Implementation and verification notes

The implementation observations and test totals below describe historical integration checks, not current-suite verification. Machine-specific scratch locations are omitted. For a new run, set `TMPDIR` to an approved local scratch directory and use a fresh pytest base directory.

- Book/page projection payloads and support edges are persisted as typed JSON in project-scoped SQLite rows, not a second Warehouse. Freshness is evaluated in a consistent read transaction against current canonical rows; no stale persisted `current` flag can mask known upstream changes. Shared pages are allowed, as are separate explanations citing the same item.
- Root project revisions are deliberately conservative: even an unrelated approved edit in the same project makes a pending proposal stale. Entity revision checks additionally prevent silent structure/prose overwrites. Publication cannot demote a page while a published book still references it; archive/draft its book in the same reviewed proposal first.
- A book's `overview` is editorial. Factual section fidelity is a human-review obligation; citations cannot prove a paraphrase true. Cross-project reuse, mixed Warehouse+Library atomic transactions, deletion, nested chapters, semantic conflict discovery and new bounded library agent-context endpoints are not implemented.
- Actual RED/GREEN runs covered absent reader persistence, schema migration version/backup, snapshot validation, approval revalidation/idempotency/rejection, duplicate references, draft gaps, publication coherence, and exact pre-alteration backups. Supplemental tests exercised multi-page ordering, cyclic cross-links, restart, reviewed support refresh, registered transitive cycles, unchanged canonical counts and forced SQLite transaction rollback.
- Historical command (local scratch assignment omitted): `uv run --extra desktop --group dev --locked pytest tests/integration/test_library*.py tests/integration/test_store.py tests/integration/test_transactions.py tests/integration/test_invalidation.py tests/contracts/test_http.py -q --basetemp "$TMPDIR/library-final-verified"` → **63 passed**. Includes actual uvicorn subprocess/loopback HTTP book proposal, human approval and persisted reading, plus authenticated FastAPI transport tests.
- Concurrent full-tree check at this integration point: **149 passed, 1 failed**. The failure was the new UI capture-save test reporting `Capture service integration is not available yet`; intake registration is outside this owner's files. Earlier Library UI integration failure no longer reproduced in that run. Full-suite totals may change while other owners add tests; parent must rerun after integration.
