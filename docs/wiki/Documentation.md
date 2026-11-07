<!-- Generated mirror of docs/documentation.md; edit canonical source first. -->

# Documentation authority and feature status

**Unfinished source-only DRAFT — 0.3.0 unreleased.** This is not a finished product or a cleared binary release.

## One truth per subject

- `pyproject.toml` is the package/build version source; bundle/artifact/feed/tag values must match it. Documentation does not declare a release by mentioning a proposed version.
- [README](https://github.com/NewBww/knowledge-hub/blob/main/README.md) is the user entry point; [Product](https://github.com/NewBww/knowledge-hub/blob/main/PRODUCT.md) records intent and implemented/target distinctions; [Design](https://github.com/NewBww/knowledge-hub/blob/main/DESIGN.md) records the approved reading-room surface and tokens.
- [User guide](https://github.com/NewBww/knowledge-hub/wiki/Reading-and-Review), [privacy](https://github.com/NewBww/knowledge-hub/wiki/Privacy-and-Context), [connections](https://github.com/NewBww/knowledge-hub/blob/main/docs/curator-connections.md) and [architecture](https://github.com/NewBww/knowledge-hub/wiki/Architecture-and-API) describe current behavior.
- [Changelog](https://github.com/NewBww/knowledge-hub/blob/main/CHANGELOG.md) records user-facing changes; [version history](https://github.com/NewBww/knowledge-hub/blob/main/docs/version-history.md) records provenance, not retroactively reconstructed release snapshots.
- [Release procedure](https://github.com/NewBww/knowledge-hub/blob/main/docs/releasing.md) and [maintenance](https://github.com/NewBww/knowledge-hub/wiki/Maintenance) define gates. Historical acceptance briefs and dated verification reports are not current release certificates.

## Integration checkpoint

Shared Warehouse, simple Library, capture/Activity, human review, selected-passage revision context and bounded connection transports are present in source. ChatGPT/Codex inference remains blocked. Live provider account validation and final native packaging/signing/license acceptance are not implied by synthetic tests.

Native mixed file/folder selection, scoped read-only sources and durable Curator jobs are integrated in the 0.3.0 source. Explicit per-job selection is separate from persistent grants; there is no bulk folder upload. Jobs recover on reopen and stop on Quit, with no independent background service configured. Human review remains required before canonical apply. Cross-book follow-up/outbox orchestration remains incomplete.

The working Reading room is the authority for its approved visual design; old prototypes do not authorize a redesign. Version 0.3.0 is the initial public implementation baseline, not evidence of older full-source snapshots or a published binary.

## Verification on hand and release limits

- The integrated source run on November 7, 2026 completed with **601 passed, 3 skipped** in approximately 241.1 seconds. This is a dated local result, not a hosted CI result or a promise about later edits. Review/approval late-response guards are covered by source/browser tests.
- A real isolated frozen local-preview build exercised loopback serving, authenticated browser bootstrap, human approval, restart persistence, a 390px layout without horizontal overflow, clean owned-process/listener shutdown and Unicode DOCX worker extraction.
- Earlier frozen QA reached the browser/files-only fallback. The source now includes a narrow app-owned WebKit reply bridge compatible with strict CSP. Later QA of the unchanged rebuilt local-preview app opened the real read-only native panel and verified Cancel with no new grants. Positive mixed file/folder selection, returned URLs, context chips, durable grants and revocation remain **BLOCKED by the permitted background input path**, not verified passes or a demonstrated mixed-selection product defect.
- The unchanged rebuilt local-preview artifact rendered on repeated launches: a white initial frame at one second was followed by the Library/composer at three seconds. No persistent blank-window defect or production rendering repair was established. Source-native startup/reply/dispatch/cancellation coverage passed **21 tests**; supplemental content-view attachment observations characterize source behavior, not frozen positive-selection success.
- Hosted CI still fails at startup with zero jobs after the runner-label correction to `macos-15-intel`; no green hosted gate or main merge is claimed. The local source result includes the keyboard duplicate-selection focus regression repair and is not hosted CI.
- An opt-in native lxml candidate was integrated into the QA app. Exact frozen native/runtime licensing and `proxy_tools` metadata reconciliation remain open; candidate success does not clear redistribution.
- The preview is local-only, ad-hoc signed, not Developer ID signed, not notarized and not release-cleared. Existing license gates must remain fail-closed. No publication, certification or complete delivery is claimed.
- Earlier static-rule review has limited rule coverage and adjudicated false positives; the latest changes have not been rescanned. It is not comprehensive Apiiro/elttam coverage or a security certification.

Keep raw reports, machine paths and private originals out of public docs. Before protected-main merge or finished release, rerun the relevant checks against the exact candidate and reconcile [acceptance](https://github.com/NewBww/knowledge-hub/blob/main/docs/next-version-acceptance.md), [packaging](https://github.com/NewBww/knowledge-hub/blob/main/docs/desktop-packaging.md) and [release gates](https://github.com/NewBww/knowledge-hub/blob/main/docs/releasing.md).

## Source DRAFT versus finished delivery

An explicitly unfinished source-only DRAFT may be shared without completing binary acceptance or frozen-payload licensing. Before any public push, review the exact allowlisted bytes for privacy, secrets, authorship/origin and intentional attribution; DRAFT visibility is still public. This documentation does not resolve ownership or legal clearance. Protected-main merge and finished release still require actual green CI, applicable acceptance checks and relevant license gates; no force push or protection bypass is authorized.

## Wiki mirror

[Wiki source](https://github.com/NewBww/knowledge-hub/blob/main/docs/wiki/README.md) mirrors selected canonical pages with rewritten links. Edit canonical pages first, regenerate their mirrors, validate both, then publish only after source privacy review. Wiki publication is a separate Git operation; nothing here publishes automatically.

## Validation

Check Markdown file/anchor targets against the publication allowlist, not merely files present in a developer checkout. Check Wiki page targets separately because extensionless Wiki links resolve differently. Source-link examples must point to implemented routes; requested/in-flight routes must be labelled, not linked as functioning APIs. Scan public prose for personal absolute paths, private references, raw audit output and credentials. Do not publish local screenshots/reports simply because another document links to them.
