<!-- Generated mirror of docs/privacy-and-context.md; edit canonical source first. -->

# Privacy, permissions and context

[Documentation home](https://github.com/NewBww/knowledge-hub/wiki/Home) · [Status and limits](https://github.com/NewBww/knowledge-hub/wiki/Documentation)

**On this page**

- [Local-first does not mean no disclosure](#local-first-does-not-mean-no-disclosure)
- [Separate controls](#separate-controls)
- [Scoped local context](#scoped-local-context)
- [Durable work and local retention](#durable-work-and-local-retention)
- [Provider disclosure](#provider-disclosure)
- [Retention and deletion](#retention-and-deletion)

**Unfinished source-only DRAFT — 0.3.0 unreleased.** This is not a finished product or a cleared binary release.

## Local-first does not mean no disclosure

The canonical SQLite database, captures and application settings live under the selected local data root, normally `~/Library/Application Support/Knowledge Hub`. The desktop server binds loopback, not a shared LAN service. Local files are not encrypted by the application; use OS account controls, disk encryption and protected backups. A process with your account's filesystem rights is outside the app's agent permission boundary.

Reading and search need no model. Saving a capture locally does not itself authorize a provider request. Enabling managed processing with the required consent/access gates can send bounded task text and instructions through the selected connection. External MCP clients may forward retrieved knowledge or original attachments to their own services. The app cannot retract those downstream copies.

## Separate controls

- Human desktop session: review, approval, authentication, consent and enablement.
- Agent credential/client: permitted retrieval and pending proposals, never self-approval.
- Shared capture-access grant: includes future captures until revoked; it is not per-book isolation. Migration must not widen a historical scoped grant silently.
- Managed connection readiness: selected destination/model, human consent, supported transport and successful synthetic check; a check does not validate every account entitlement or future request.

Disable capture access in the app to stop subsequent capture reads/claims through that boundary; disable managed processing separately. Revocation does not erase material already read, submitted proposals or remote traces. Disconnect external clients and review their credentials/configuration as appropriate. Do not expose loopback ports/tokens to other machines.

## Scoped local context

The desktop native mixed picker registers selected files and directories as persistent, read-only source grants. It does not copy an entire folder into capture storage or start a watcher. The browser cannot create a grant by supplying an absolute path; the native bridge takes no path argument. Human-session inspection uses opaque source IDs and validated relative paths; absolute source roots stay in the local grant database. This is ordinary user-consented filesystem access, not an OS sandbox or a security-scoped-bookmark implementation. Earlier frozen QA reached the browser/files-only fallback. The source now includes a narrow app-owned WebKit reply bridge compatible with strict CSP. Later QA of the unchanged rebuilt local-preview app opened the real read-only native panel and verified Cancel with no new grants. Positive mixed file/folder selection, returned URLs, context chips, durable grants and revocation remain **BLOCKED by the permitted background input path**, not verified passes or a demonstrated mixed-selection product defect. Do not treat successful panel opening/cancellation as verified packaged grant creation.

Hidden, credential-like, generated and package paths are excluded by policy; symlink traversal is refused. Bounded listing/read/search applies current ignore rules and rechecks grant/root identity. These controls reduce accidental disclosure but cannot identify every secret embedded in an otherwise allowed text file. Choose narrow, non-sensitive roots; do not grant your whole home or account directories.

Authorizing a source and selecting it for a job are separate actions. Each instruction uses only its explicit source IDs. Jobs pin generation/content digests and revalidate sources and connection consent before pending publication; changed or revoked sources block/stale the work rather than silently expanding context. Revoking a grant stops subsequent access through that grant, not remote copies or already-created proposals. Unchecking a source only removes it from the current draft, not the persistent grant.

Saved attachments and revision-bound selected passages remain separate context routes. A passage contains only the explicit selection and locator, not permission to fetch unrelated files. See [the workflow](https://github.com/NewBww/knowledge-hub/wiki/Reading-and-Review#use-scoped-local-context) and [verification limits](https://github.com/NewBww/knowledge-hub/wiki/Documentation).

## Durable work and local retention

Curator job records/checkpoints persist locally in `curator-jobs.sqlite3`; source roots/grants live in `context-sources.sqlite3`, alongside the canonical store. A prepared checkpoint can contain proposed text derived from selected sources. Directory references can retain relative filenames and content digests. These are sensitive application data, not merely anonymous queue counters. The capture seven-day retention setting does not promise expiry of job records, grants, accepted knowledge or backups.

Work pauses on Quit and eligible jobs recover on reopen after revalidation; no independent background service is configured. Cancellation does not retract an existing pending proposal, approved fact or provider trace. Review proposal state separately and retain protected backups.

## Provider disclosure

The destination is the service **and any routed underlying provider**, not merely the CLI or loopback proxy. Remote inference may cost money. OpenRouter has constrained routing in this implementation; these constraints are not a universal no-retention guarantee. Official CLIs can retain local traces, and provider safety/legal/account records may remain. Review the actual account terms/settings. A training opt-out is not equivalent to zero retention. ChatGPT/Codex execution is currently blocked; see [transport-specific limits](https://github.com/NewBww/knowledge-hub/wiki/Connections).

App-owned OpenRouter secrets use the macOS credential store, with no plaintext fallback. Official clients own their authentication and may consult OS account stores; an isolated HOME is not proof of complete account-store isolation. Never paste passwords, API keys, OAuth codes or tokens into captures, issues, MCP arguments or screenshots.

## Retention and deletion

The capture API accepts 1–30 days, default seven; the current UI asks for seven. Expired capture directories are removed when the intake service is initialized or accessed, not by a guaranteed always-running expiry daemon. Closing the app can delay cleanup. Activity offers discard/cleanup workflows; verify their result and heed a cleanup failure even if a review decision succeeded.

Accepted knowledge, revision/evidence records, backups and client/account profiles have different lifetimes; capture deletion is not an all-data eraser or secure physical overwrite. Backups and remote services require their own deletion policy. Uninstalling the app leaves its data root and OS-managed credentials intact. Inventory both before deliberate removal; do not delete data while any app/MCP process is using it.

Implementation references: [intake lifecycle](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/intake.py), [shared permission routes](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/shared_http.py), [desktop boundary](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/desktop.py), [connection implementation](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/connections.py).
