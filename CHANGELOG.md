# Changelog

**Unfinished source-only DRAFT — 0.3.0 unreleased.** This is not a finished product or a cleared binary release.

User-facing changes are recorded here. Source metadata and verified tags identify releases; historical local installers are not reconstructed source releases. See [version provenance](docs/version-history.md).

## Unreleased

### Documentation and repository readiness

- Added task-oriented installation, reading/review, privacy, troubleshooting, backup and integration guidance.
- Added canonical-document Wiki mirrors, secure read-only CI, dependency-update configuration and sanitized community templates.
- Documented independent source privacy, native runtime, updater, signing and frozen dependency-license gates.

### Reading room, scoped context and Curator work

- Integrated native mixed file/folder selection with persistent read-only grants, exclusions, revocation and explicit per-job source selection; no bulk folder upload.
- Added durable foreground-resumable Curator jobs, checkpoint/restart recovery, bounded retries and pending-proposal readback. Work stops on Quit; canonical apply remains human-only.
- Preserved drafts and guarded review/approval against late responses after navigation.
- Verified the integrated source suite and an isolated frozen local-preview HTTP/browser run, including human approval, restart persistence, narrow layout and Unicode DOCX extraction. Earlier frozen QA reached the browser/files-only fallback. The source now includes a narrow app-owned WebKit reply bridge compatible with strict CSP. Later QA of the unchanged rebuilt local-preview app opened the real read-only native panel and verified Cancel with no new grants. Positive mixed file/folder selection, returned URLs, context chips, durable grants and revocation remain **BLOCKED by the permitted background input path**, not verified passes or a demonstrated mixed-selection product defect.

This is unfinished source-only DRAFT work, not a finished release. Exact public-byte privacy/secrets/authorship review remains required; protected-main and binary-release gates are not waived. Signing/notarization, exact frozen dependency/license reconciliation (including native libraries and `proxy_tools` metadata), live-provider and native/updater acceptance remain separate gates. Cross-book follow-up/outbox processing remains incomplete.
