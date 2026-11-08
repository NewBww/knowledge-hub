# Knowledge Hub

**Unfinished source-only DRAFT — 0.3.0 unreleased.** This is not a finished product or a cleared binary release.

A local-first macOS reading room for knowledge that people and agents maintain together.

**Read in Library. Inspect evidence in Warehouse. Review before accepting changes.**

Knowledge Hub stores canonical knowledge in SQLite on your Mac. Reading and search do not require a model account. An optional bounded Curator or your own MCP agent can prepare changes; neither can approve its own work.

## Start here

- [Install and capture your first knowledge](docs/getting-started.md)
- [Library, Warehouse and human review](docs/user-guide.md)
- [Privacy, permissions and retention](docs/privacy-and-context.md)
- [Connections and their actual limits](docs/curator-connections.md)
- [Use your own agent](docs/agent-bootstrap.md)
- [Troubleshooting and keyboard access](docs/troubleshooting.md)
- [Backup and migration](docs/backup-and-migration.md)

An explicitly unfinished source-only DRAFT may be shared without completing binary acceptance or frozen-payload licensing. Before any public push, review the exact allowlisted bytes for privacy, secrets, authorship/origin and intentional attribution; DRAFT visibility is still public. This documentation does not resolve ownership or legal clearance. Protected-main merge and finished release still require actual green CI, applicable acceptance checks and relevant license gates; no force push or protection bypass is authorized.

## macOS installation

Only install a candidate whose release notes identify its version, architecture, digest and signing limitations. The repository's presence is not evidence that a distributable binary has cleared release gates. Follow [installation and verification](docs/getting-started.md#packaged-app). Current packaging uses an **ad-hoc local-test signature**, not Apple Developer ID signing or notarization. Binary dependency review, native updater acceptance and publication are separate gates; see [releasing](docs/releasing.md).

The default data directory is `~/Library/Application Support/Knowledge Hub`, outside the app. Quit before replacing the app and back up your data first. Removing the app does not delete knowledge or account state.

## Source quickstart

On macOS, install Python 3.12 and `uv`, then run from the checkout:

```sh
uv sync --extra desktop --group dev --locked
uv run --locked --extra desktop --group dev knowledge-hub
```

For an isolated trial, append `--data-dir "$HOME/Knowledge-Hub-Trial"`; use a new directory, not an existing personal knowledge store. No hosted database, Hermes account or inference credential is required to launch and read. See [Contributing](CONTRIBUTING.md) for the full test setup, including Chrome.

## What works, and what is not promised

- One shared Warehouse; no required projects. Library books are readable subjects, not containers that own facts. Knowledge can exist without books.
- Local capture of text and bounded attachments; Activity distinguishes saved work from actual processing. PDF/DOCX text extraction is bounded; images are validated, not OCR-read.
- Pending knowledge and reading-surface proposals, revision checks, evidence and explicit human approval/rejection. Dependency impact covers registered relationships, not every possible contradiction.
- Client-neutral stdio MCP with progressive retrieval and explicit omissions. Remote clients can forward anything they read: local storage is not a provider privacy guarantee.
- Settings separates connection choice, model selection, sign-in, synthetic checking, disclosure consent, capture access and processing enablement. ChatGPT/Codex execution remains blocked; other routes have version/capability limits.
- A native mixed file/folder picker registers scoped, read-only local context. Select sources explicitly for each durable Curator job; this is not bulk folder upload. Jobs stop on Quit and recover eligible work on reopen after revalidation; no closed-app processing is configured; canonical changes still require human review. See [the workflow](docs/user-guide.md#use-scoped-local-context).
- Arbitrary source polling, automatic connector imports, universal freshness and completed cross-book follow-up/outbox processing are **not established capabilities**. The strict-CSP source bridge repair is included. Later frozen QA opened the real native panel and verified cancellation, but positive mixed selection/grant/revoke acceptance remains blocked. Public binary gates remain open; see [current evidence](docs/documentation.md).

For the implementation/roadmap boundary see [Product](PRODUCT.md), the [roadmap and release backlog](docs/roadmap.md), and [documentation status](docs/documentation.md). Source metadata is authoritative for the version; an untagged checkout is not a release.

## Developer and maintainer reference

[Developer quickstart](docs/developer-quickstart.md) · [Code map](docs/code-map.md) · [Architecture and API](docs/architecture.md) · [Design](DESIGN.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md) · [Release maintenance](docs/maintenance.md) · [Wiki maintenance](docs/wiki-maintenance.md)

Application source is [MIT licensed](LICENSE). Dependency licenses and frozen-bundle obligations are separate; [third-party notices](THIRD_PARTY_NOTICES.md) do not by themselves certify a binary for redistribution. User knowledge is not licensed by this repository.
