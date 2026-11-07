# First-release revision integration contract (historical)

This is the historical project-scoped, external-agent-only integration brief, not the current implementation contract. Its provider-account exclusions, project routes and updater limitations were superseded by the 0.3.0 shared Warehouse and optional bounded Curator integration. Preserve the original scope and observations below as history. For current behavior see [README](../README.md), [Curator connections](curator-connections.md), [acceptance gates](next-version-acceptance.md) and [releasing](releasing.md).

User review now makes Library/Warehouse/Curator, single-box multimodal capture, local-only knowledge persistence, and an application icon first-release requirements. Selective external publication remains deferred. This is implementation scope, not a completion claim.

## Harness boundary and privacy (latest owner clarification supersedes embedded-provider plans)

- Knowledge Hub is a local knowledge system, not an AI harness, chat application, model gateway or connector platform. It does not maintain provider accounts/API keys, model runners or duplicate connector configurations.
- Two equal ingestion routes share the same application services: (1) paste text/images/files/folder-selected content in the app into a local pending-intake queue; (2) the user's existing agent submits selected facts/findings, evidence and proposed organization through MCP without needing an app paste first.
- The external harness owns its models, credentials, source connectors, reasoning and scheduling. Its agent decides when it has durable knowledge worth proposing. Curator is that agent's knowledge-maintenance role, not a required embedded model.
- Pasted input is not magically organized without a connected agent. Show awaiting-agent, processing/proposed/needs-review/error states accurately; do not simulate successful AI processing. The app remains usable to capture and review offline.
- All canonical knowledge, captures and books stay in local app data, never a cloud database or app bundle. Raw captures are local transient work items, not maintained conversation archives; cleanup follows explicit lifecycle/retention rules.
- No automatic cloud model egress, harness launch, connector invocation, provider fallback or external-client registration. Users deliberately connect the MCP client they already trust; bounded selected reads limit unnecessary disclosure.
- A locally installed harness can send retrieved knowledge to a cloud model. Hub cannot verify or enforce its downstream provider training/retention policy once it has read access. Warn clearly at agent connection/access setup; do not claim that local storage, a client name or a no-training checkbox guarantees confidentiality. Provider/account privacy controls belong in the user's harness and organizational policy.
- Do not collect provider keys or present a provider-policy approval screen inside Hub. App-controlled MCP read scopes, request sizes, audit metadata and human review remain enforced; no raw content/secrets in logs.
- Treat captured text, attachments and submitted agent output as untrusted data. No shell/SQL execution, instruction activation or automatic URL fetching. Evidence supports claims but is not itself proof that an agent's assertion is true.
- Agents submit pending proposals, never self-approve accepted facts or silently overwrite stronger local knowledge. Preserve project scope, revisions, idempotency, explicit uncertainty and registered impact analysis.

## Library-first interface (latest owner clarification)

- Library is the main page and visual center of the application, not merely a default tab that immediately redirects to the first page. Books have a recognizable browse/open flow; reading remains the primary task.
- Curator is an explanatory name for the external agent's knowledge-maintenance role, not a separate destination in navigation. Add knowledge and saved intake/review are contextual Library workflows. Preserve both app capture and direct MCP contribution.
- Settings contains agent connection/setup and application update checks. Neither requires a selected project merely to open the help/status screen. Project-specific capture permissions must retain their explicit scope and human consent.
- Keep Warehouse, canonical support inspection and human review accessible without competing equally with the Library home. Do not remove intake lifecycle, draft preservation, attachment inspection or downstream-provider disclosure safeguards while simplifying navigation.
- Update hosting remains deliberately unconfigured. Moving the control into Settings does not implement signed download/install/relaunch or authorize a release host.

## Parallel ownership

1. Library backend owner: core.py, store.py, new library.py, library_http.py and library_models.py; tests for library; docs/library-contract.md. DO NOT edit http.py/mcp.py/web/packaging/pyproject.
2. Intake/privacy owner: new intake.py, curator.py, privacy.py, intake_http.py and associated models/tests; docs/curator-contract.md. DO NOT edit store.py/core.py/http.py/mcp.py/web/packaging. Can edit pyproject.toml/uv.lock for actual supported extractors if needed; preserve desktop extras and dev group.
3. UI owner: web assets, frontend/browser tests, DESIGN.md/surface brief. Use the adapter contract below. Do not edit backend or packaging.
4. Packaging owner: tools/build_macos.py, desktop packaging tests/docs and public icon assets; no backend/UI edits or version bump.
5. Parent integrates router registration, MCP tools, reconciles version/docs and exercises full native/bundle paths.

## Proposed HTTP adapter contract (freeze or report needed changes early)

Both adapters expose `register(app, store)` to attach routes. Existing auth middleware already sets request.state.human; new approval/settings/processing/disclosure mutations must check it and raise DomainError('approval_required',403). Existing agent Bearer is read/propose, not human.

Library:
- GET /api/projects/{project_id}/books => {books:[{id,title,purpose,revision,state,page_count}]}
- GET /api/projects/{project_id}/books/{book_id} => book with ordered pages and support state
- GET /api/projects/{project_id}/pages/{page_id} => page with sections/support IDs and states
- POST /api/projects/{project_id}/library/changes => typed pending library proposal
- GET /api/projects/{project_id}/library/changes => {changes:[...]}
- POST /api/projects/{project_id}/library/changes/{change_id}/approve or /reject => human only
- Current /knowledge remains Warehouse endpoint; current /changes remains reviewed canonical updates.

Intake:
- POST /api/projects/{project_id}/captures => JSON {text,files:[{name,media_type,content_base64}],intent?}; folder upload uses relative paths in name, not arbitrary server filesystem path. Need limits, traversal protection, unsupported/password-protected-file reporting, no symlink walks or implicit private-directory reads.
- GET /api/projects/{project_id}/captures => {captures:[metadata only]}
- GET /api/projects/{project_id}/captures/{capture_id} => bounded local capture inspection/status
- DELETE /api/projects/{project_id}/captures/{capture_id} => human only cleanup
- GET /api/curator/status => local intake/agent workflow capabilities; no provider settings or API keys
- Agent services expose bounded pending-capture discovery/inspection and typed curation-result submission for parent MCP integration; direct already-curated knowledge proposals do not require a capture.
- Curator output is submitted by the user's external agent as a validated draft/proposal with canonical Warehouse changes and book/page suggestions, never direct approval. No internal provider invocation or fake AI success. Unsupported modalities clearly remain unprocessed with a reason.
- Intake owner can use existing Store.propose for warehouse drafts. For library draft generation, use library owner's documented Python service or return a typed suggestion the parent integrates; no circular dependency required.

Use isolated synthetic fixtures, strict incremental TDD and real HTTP/subprocess checks. Report exact supported formats and actual provider execution versus local fake-server protocol tests. No real provider calls with private knowledge, no external publication, commits, pushes or installations into /Applications.
