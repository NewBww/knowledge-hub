# Knowledge Hub

**Unfinished source-only DRAFT — 0.3.0 unreleased.** This is not a finished product or a cleared binary release.

<!-- impeccable:product-schema 1 -->

## Platform

web

The working interface is a local web application hosted in a dedicated macOS desktop window, not a browser tab. It is not a native SwiftUI interface. Other operating-system packages are not yet committed.

## Stack

Python + SQLite with a lightweight semantic HTML/CSS/JavaScript interface and a native WebKit shell (pywebview). FastAPI/Pydantic and the official Python MCP SDK share one application-command boundary. The user chose a dedicated desktop window over the initial browser-launcher proposal. Packaging must include the runtime; recipients should not install Python or use a terminal.

## Users

The owner maintains knowledge across projects. Readers include the owner, other people and agents with differing prior knowledge. Other people install the generic application and initialize their own independent knowledge.

## Product Purpose

Maintain a readable single source of accepted facts and findings. Brief corrections should become reviewed changes with explicit impact on related registered knowledge, rather than silently leaving known dependent statements current.

## Operating Context

Library-first: the main page presents books to browse and open, with measured page reading and local search. Add knowledge is a contextual Library workflow, not a separate Curator page. Curator names the knowledge-maintenance role; the requested next revision supports both an app-managed Curator and external agents through MCP. Agent setup and application updates belong in globally available Settings. Warehouse/support inspection and human review remain accessible but secondary to reading. Agents need semantic MCP access, not coordinate-driven UI interaction. Existing private readers and external publications remain untouched until an independently reviewed migration.

## Shared Knowledge and Simple Library

The 0.3.0 source implements the shared Warehouse and simple Library direction below. This supersedes historical project-first contracts; the acceptance gates distinguish source behavior from packaged verification.

- One shared Warehouse; no required project level or book-owned knowledge partitions. Subjects and tags are optional ways to explore, not mandatory capture destinations. Existing knowledge, citations, revision history and human decisions must survive a reviewed migration; existing scoped agent grants must not silently become global access.
- Library is the calm, curated reading surface; Warehouse is the secondary, comprehensive knowledge explorer. A book is a friendly name for a readable subject of any scope, without a required cover, minimum length or chapter hierarchy. Multiple books may use the same canonical knowledge.
- A new installation opens to a central input without project setup or placeholder books. Knowledge may accumulate while the Library remains empty; book creation depends on a reading need and adequate support for its intended scope, not an arbitrary record count.
- One input surface supports two explicit intentions: Add knowledge (default) and Request something. Text and bounded attachment capture need no destination, topic or tags. Native file/folder selection instead registers read-only context grants; explicit per-job source selection controls use, not a bulk folder upload. Requests can ask for a reading topic, explanation or change. Direct external-agent MCP proposals remain an equal ingestion route.
- Save submissions locally and keep unfinished work reachable through quiet Activity navigation. Distinguish saved/waiting for agent, actually claimed/in progress, ready for review, and accepted. An MCP connection alone does not establish active processing. The optional app-managed Curator processes work only after configuration and explicit human enablement; external-agent mode must not silently launch a harness.
- Review explains proposed new findings, revisions, conflicts, evidence and affected reading surfaces, with acceptance/rejection controls. Sources are transient capture work items subject to explicit retention/cleanup, not a durable conversation archive. Acceptance of knowledge need not create a book.
- A contextual change request carries its selected passage and revision. Treat that selection as context rather than ownership; factual changes follow Warehouse approval and registered dependency impact, while presentation-only changes remain reading-surface changes.
- Use cross-domain references for behavior: Cosmos for content-first exploration, Canva for the obvious input, Figma for anchored requests, and Spotify for ready-to-consume grouping. Do not copy social feeds, promotional density, editor chrome or decorative physical books. Provider configuration belongs in Settings, not the reading surface.
- Verify three distinct states: completely empty; knowledge present without books; populated Library. Preserve readable layouts, keyboard access, drafts, attachment inspection, human review and explicit disclosure consent throughout.

## Requested Next Revision: Curator Setup and Agent-Assisted Bootstrap

This requested scope expands the historical external-agent-only direction. Some bounded transports and saved account/model routes are implemented in source; the list below remains broader than verified support. The current [connection contract](docs/curator-connections.md) is authoritative for capabilities and blocked routes, not this requested target list.

- Offer two first-class paths: configure an app-managed, model-backed Curator or use an existing external agent through MCP. Neither path requires Hermes specifically. The app-managed worker is bounded to knowledge ingestion, evidence-backed proposals and reading-surface maintenance, not arbitrary shell access, general-purpose automation, a connector catalog or a replacement for the user's harness.
- Keep setup under Settings: choose a provider from maintained presets or a supported custom/local endpoint, authenticate, select one desired model for all app-managed knowledge work, verify capabilities, and explicitly enable processing. Do not expose separate Curator/ingestion model assignments, including advanced overrides. The app controls task-specific instructions, bounded tool permissions, context and isolated sessions for ingestion, reconciliation and reading-surface maintenance, using the same selected model. Model availability is discovered where supported, with validated manual identifiers where needed; adapter/protocol and model capabilities determine compatibility.
- Initial-release connection targets are ChatGPT, GitHub Copilot, OpenRouter, OpenCode, Gemini and Hermes. Present these as connection choices rather than pretending they are all inference providers. Planned supported routes: ChatGPT through official Codex CLI sign-in and bounded execution; Copilot through the official GitHub Copilot CLI; OpenRouter through its documented application PKCE authorization/API-key flow; OpenCode through its CLI and configured provider; Gemini through official Gemini CLI Google sign-in or supported API-key access; Hermes through its CLI and configured provider/model. Native OAuth and CLI execution are alternatives, not requirements to implement both for every connection. Verify exact supported versions, account entitlements, model selection and bounded non-interactive execution before marking any adapter usable. The requested six-target scope is not a claim that these integrations already work in the app.
- Keep one active connection and one explicit selected model for app-managed work. Through OpenCode or Hermes the selected model belongs to that client's configured underlying provider, not to an invented OpenCode/Hermes model service. Do not modify the user's global harness defaults, reuse unrelated conversation history or silently substitute another model/provider. Show missing CLI, sign-in required, unsupported capability and ready states; provide installation/sign-in guidance with human consent rather than claiming bundled CLI availability.
- Authentication belongs to the provider or authorized CLI, not the model. Offer API keys and provider-approved OAuth/device flows only where actually supported for this application. CLI-backed connections invoke the official client using its own supported authentication; do not extract, copy or replay that client's tokens in a custom HTTP client. App-owned credentials belong in the operating-system credential store; official CLIs retain their own credential management. Keep credentials out of source, logs, exports, MCP responses and the knowledge database. CLIs are an authorized execution path, not an exemption from privacy controls: isolate app-owned workspaces/task sessions, enforce tool/filesystem limits rather than relying on prompts alone, disclose any client-side history/retention, and require a synthetic readback-verified test for each adapter before readiness.
- Keep canonical knowledge local. Remote inference sends selected task material to the selected provider and can incur costs; disclose destination, content scope and applicable provider retention/training terms before consent. Do not guarantee no training or retention without verified applicable terms. Do not silently fall back to another provider or expand disclosure scope. Preserve a local-endpoint option and basic model-free reading/search.
- Publish a versioned agent-readable bootstrap guide through MCP discovery/resources, available before any knowledge exists or Curator is configured. Explain current capabilities, supported setup paths, human-only steps, privacy boundaries, exact schemas, recoverable errors and readiness criteria. Initial connection/install instructions must also be available outside MCP so discovery is not circular.
- Provide narrowly scoped setup operations for inspecting redacted configuration/readiness, listing supported provider/auth/capability metadata, staging validated non-secret model assignments, requesting a human auth/consent handoff and running bounded diagnostics. Exclude arbitrary file writes, shell commands and direct database edits. Configuration changes affecting provider destinations, models, spend or disclosure require human confirmation; authenticated agents cannot enable themselves, retrieve credentials, grant access or accept their own knowledge proposals.
- Support the external-agent instruction 'setup knowledge base' by discovering state, reading the guide, proposing configuration, pausing for secure human sign-in/consent, and verifying readiness. Use a clearly synthetic connection and proposal smoke test, never owner knowledge for an automatic diagnostic. Verify claims with readback; keep temporary test material separate from accepted knowledge and remove it after the check. Report blocked, unconfigured, paused and ready states honestly.
- Both execution paths use the same validated domain commands, review rules and idempotent work-claim boundary so they cannot process a capture twice or bypass approval. Readiness means configured authentication, compatible models, human-approved access/processing and a successful bounded workflow check; it does not mean knowledge already exists or any book has been published.

## Future Feature: Confluence-Compatible Reading and Selective Publication

Requested future scope, not implemented or verified compatibility. No target release number has been assigned.

The user's requirements are:

> Another feature i wanted to add might be the options to publish some pages or book into user's confluence space or specified path

> Design with the mind that in the future i want the book to be able to publish with fully compatible confluence page so the reading page can includes graphs, tables, images, or anything that can be put into confluence

- Preserve this as a reading/content-design requirement now, not merely a future plain-text export button: rich book/page content must be designed with eventual Confluence publication in mind.
- Support selective publication of chosen pages or a book into the user's Confluence space or specified path. Confluence remains an optional publication destination; canonical knowledge stays local, and publication requires explicit destination/content authorization.
- The compatibility target includes graphs, tables, images and other Confluence-supported content. Exact content representations, supported Confluence variants and fidelity/round-trip behavior remain to be specified and tested; do not claim full compatibility from HTML rendering or historical one-off Confluence extraction.
- Nested books/pages and navigable outlines are related reading requirements, not evidence that an export/publishing adapter exists. Automatic synchronization or bidirectional editing is not established by these requests.

## Capabilities and Constraints

- One canonical store and shared application commands across the UI, API and MCP.
- Facts/findings, not a maintained archive of peer conversations.
- Explicit unresolved conflicts, revisions and needs-review states for known affected dependents.
- Local reading and search require no model service or hosted database.
- Agent consumption is progressive and bounded: compact discovery/search, task-scoped context with only necessary registered prerequisites and uncertainty, then full details/evidence/history on explicit request. Responses identify revision, included/omitted coverage and continuations. Storage compactness is not a token-efficiency guarantee; do not dump a project or source archive into each agent request, and do not claim model-independent exact token counts.
- Easy installation and sharing at low operating cost. Desired macOS delivery is a self-contained .app in a .dmg; private knowledge must live outside the app bundle and source repository.
- No cloud knowledge database, cloud synchronization or hosted knowledge-storage roadmap is in scope. All canonical knowledge stays on the owner's machine. The requested optional app-managed Curator may use local or remote inference, while external clients continue to own their own models, credentials, source connectors and reasoning. Neither local inference nor a particular external harness is required.
- Ingestion has two equal routes: single-box local capture for an explicitly enabled app-managed Curator or authorized external agent to process, and direct agent submission of durable findings/evidence/proposals through MCP. Both converge on evidence-backed pending changes and human review. Built-in provider setup is optional; do not duplicate external source connectors or require external-agent users to configure a second provider.
- Cloud inference is permitted only through explicitly configured and consented task routes. Connecting MCP grants the chosen client selected knowledge access; that client may also use cloud models independently. Hub controls its own disclosure/permission boundary but cannot guarantee downstream provider training or retention. Keep confidentiality warnings accurate rather than offering a false no-training guarantee, and never silently launch an external harness.
- First-release scope includes Library books/pages over shared Warehouse records, Curator-assisted single-box capture, scoped file/folder context selection, durable foreground-resumable jobs, and an application icon. The earlier topic-only vertical slice is not the accepted first release.
- Approval-first semantic updates. Agents cannot grant themselves human approval.
- New installations start empty. Synthetic examples must be clearly labelled and explicitly loaded.
- Every installer may use their own agent client, model provider and configuration. Hermes is an optional client, not a required application dependency. Maintain discoverable, versioned MCP/API contracts and clear extension boundaries so agents can maintain and extend the source without direct database edits or hidden environment assumptions.
- Do not claim universal semantic freshness or automatic discovery of unregistered dependencies.

## Implemented scoped context and durable jobs

The Reading room keeps Library, Warehouse, Activity and human review distinct. Native mixed selection registers read-only source grants; granting access and selecting sources for a particular instruction are separate steps. Local-context HTTP inspection and job control require a human session; an agent bearer cannot create grants or invoke these human routes. Grants persist locally, remain subject to current exclusions and revocation, and are not App Sandbox security-scoped bookmarks. Earlier frozen QA reached the browser/files-only fallback. The source now includes a narrow app-owned WebKit reply bridge compatible with strict CSP. Later QA of the unchanged rebuilt local-preview app opened the real read-only native panel and verified Cancel with no new grants. Positive mixed file/folder selection, returned URLs, context chips, durable grants and revocation remain **BLOCKED by the permitted background input path**, not verified passes or a demonstrated mixed-selection product defect.

Jobs pin source references and digests, save checkpoints, fence worker leases and replay pending proposal publication idempotently after interruption. The host runs the worker while the app is open and stops it on Quit; reopen recovers eligible work after revalidation. No LaunchAgent or closed-app processing is configured. Ready for review means a pending proposal, never automatic canonical apply. Completed cross-book follow-up/outbox orchestration is not implemented. See [current workflow](docs/user-guide.md) and [privacy boundaries](docs/privacy-and-context.md).

## Evidence on Hand

The source preview implements a shared SQLite Warehouse, reviewed Library projections, local capture, external-agent MCP proposals, bounded retrieval and a dedicated macOS WebKit app with an application icon whose publication provenance remains subject to separate review. The bounded app-managed Curator and connection routes are optional; installed-client discovery is not proof of safe execution or authentication. Sparkle provides the native manual-update mechanism, but public feed publication, licensing clearance and packaged integration verification are separate gates. Selective external publication and portable knowledge sharing remain future work. See the public [acceptance gates](docs/next-version-acceptance.md) for what must be verified; historical local reports are not release certificates. No private content may enter source, tests, screenshots or release artifacts.

## Product Principles

1. Understanding before administration: reading is the primary workflow.
2. One accepted fact model, multiple faithful projections.
3. Known uncertainty and impact are visible, never hidden behind freshness decoration.
4. Local ownership and portable data without model-dependent basic use.
5. Installation and application upgrades must not bundle or erase knowledge.

## Accessibility & Inclusion

Readers have differing levels of domain knowledge. Use progressive detail, accessible labels, keyboard navigation, readable line lengths and narrow-window layouts. No product-specific assistive-technology standard has been selected yet.

## Open Decisions

The source includes manual native Sparkle checks and human-confirmed installation support. Public feed/release publication, third-party binary licensing clearance and actual packaged upgrade acceptance remain open; source integration does not verify signed download/install/relaunch on a user's machine. Older previews require manual replacement to bootstrap updater support. Developer ID signing/notarization and backup retention remain separate decisions. See [releasing](docs/releasing.md).
