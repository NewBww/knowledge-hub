# Reading, capture and review

**Unfinished source-only DRAFT — 0.3.0 unreleased.** This is not a finished product or a cleared binary release.

## Three surfaces, one canonical store

**Library** is the calm reading surface. Books are subjects of any useful size, with optional organization rather than mandatory covers or chapter hierarchies. Several books can reference the same facts.

**Warehouse** is the comprehensive explorer of accepted granular knowledge, evidence and state. Search is local. Needs-attention views expose registered uncertainty or invalidated dependencies; they do not detect every real-world change.

**Activity and review** show saved captures and pending proposals. Saved, waiting, claimed/in progress, ready for review and accepted are different states. A connected MCP client or signed-in provider alone is not processing evidence.

## Add knowledge

Use the contextual input, paste text or upload supported attachments, inspect the selection, then send. Native file/folder selection is a separate read-only context grant, not a bulk folder upload. No destination, tags or project are required. The current capture boundary permits up to 20 files, 5 MiB each and 20 MiB combined. UTF-8 text, text-layer PDF and DOCX have bounded local extraction; encrypted, unsupported and scanned-without-text material remains explicitly unprocessed. Validated images are not automatically OCR-read.

Captures are temporary work items, not a durable chat or document archive. The current UI requests seven-day retention. Check Activity and retain your own authoritative originals elsewhere; see [retention](privacy-and-context.md#retention-and-deletion).

## Use scoped local context

**Packaged acceptance is incomplete.** Earlier frozen QA reached the browser/files-only fallback. The source now includes a narrow app-owned WebKit reply bridge compatible with strict CSP. Later QA of the unchanged rebuilt local-preview app opened the real read-only native panel and verified Cancel with no new grants. Positive mixed file/folder selection, returned URLs, context chips, durable grants and revocation remain **BLOCKED by the permitted background input path**, not verified passes or a demonstrated mixed-selection product defect. The workflow below describes the implemented source contract, not completed frozen positive-selection acceptance.

1. In the desktop composer, use the local-context attachment action. One native picker accepts files and folders together. Approve only the narrow roots needed for the task; cancelling grants nothing. If the native bridge is unavailable, do not bypass it by entering a path.
2. Inspect the named sources and their file/directory and active/revoked states. Use each source's checkbox to select it **for this instruction**. A stored grant is not permission to include every source in every job. Revoke removes future access through that grant; unchecking only changes your current draft.
3. Enter what the Curator should learn, then send. Use local context separately from uploaded attachments or selected-passage requests; combining these routes is rejected and preserves the draft. A context job accepts up to ten explicit source IDs and a 2,000-character instruction. Only bounded supported text is read; a large selection can fail its limit rather than imply complete analysis.
4. Open **Activity**, inspect **Curator work**, and refresh status. Configuration, consent, compatible transport and processing enablement are still required. Saving a job is not evidence that inference ran.
5. When ready, use **Review proposed knowledge**. Compare the pending proposal and evidence before accepting; the job never applies canonical changes itself.

Hidden/secret/generated paths, symlinks and ignored content are excluded. Ordinary allowed text can still contain sensitive information: inspect it before granting access or consenting to remote inference. These grants are not watched folders, arbitrary filesystem tools or an OS sandbox. See [privacy and revocation](privacy-and-context.md#scoped-local-context).

## Resume Curator work

Jobs save local state/checkpoints and recover eligible work when the app reopens. **Quit stops processing**; no independent background service is configured. Reopening may require current source access, unchanged content and the same approved connection/model policy. An interrupted provider request is not a guarantee of exactly-once billing; proposal replay prevents duplicate local pending publication, not remote charges.

| Status | Meaning and next step |
| --- | --- |
| Queued / running | Saved versus actually claimed work; refresh for current state. |
| Paused / retry wait | Interrupted work or bounded transient retry; reopen or inspect before retrying. |
| Blocked | Fix the reported consent, connection or source-access problem; retry only after inspection. |
| Stale | Content or revision changed. Reread and submit a fresh instruction against current sources. |
| Failed | Inspect the reason; retries have a finite budget, not an endless loop. |
| Cancelled | This job no longer publishes new work; remote disclosure is not undone. |
| Review ready | A pending knowledge proposal exists. Human review is still required. |

Activity exposes refresh, eligible retry and cancellation controls. A review-ready job's proposal is decided in review, not removed by cancellation. Job records and source grants do not share capture expiry; keep backups protected. Automatic cross-book follow-up/outbox processing is not complete, so inspect related reading surfaces deliberately after accepting facts.

## Request a change in context

Select a passage in a Library page and use its request action. The saved context includes the page, section where applicable, passage and revision. If the page changed, the app rejects stale context rather than silently applying the request to new text. Preserve your draft, reread the current page and select again. A passage is context, not permission to fetch unrelated files or change a fact.

## Review deliberately

Compare Before and After, evidence, support references and navigation changes. A quotation can establish where a statement came from without proving it true. Inspect affected registered dependencies. Accept/reject are human operations; no setup or MCP tool grants approval authority. A stale proposal needs fresh inspection and reconciliation, not a forced retry.

Acceptance of Warehouse knowledge does not require creating a book. Reading-only arrangement changes and factual changes have different proposal paths. Capture originals can be discarded/expired independently of accepted knowledge and its citations; do not assume deleting an original erases approved facts or provider copies.

## Choose an agent path

An external MCP agent is first class; Hermes is optional. Alternatively use Settings for one active managed connection/model. Existing account profiles may be represented in Settings, but installed, signed in, checked and enabled are distinct states. Supported transport does not prove a live account works. Read [the detailed connection contract](curator-connections.md) before enabling remote processing.

Implementation references: [shared routes](../src/knowledge_hub/shared_http.py), [capture validation](../src/knowledge_hub/intake_models.py), [reader behavior](../src/knowledge_hub/web/app.js), [human approval boundary](../src/knowledge_hub/store.py).
