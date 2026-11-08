<!-- Generated mirror of docs/maintenance.md; edit canonical source first. -->

# Release and repository maintenance

[Documentation home](https://github.com/NewBww/knowledge-hub/wiki/Home) · [Status and limits](https://github.com/NewBww/knowledge-hub/wiki/Documentation)

**On this page**

- [CI is not a release certificate](#ci-is-not-a-release-certificate)
- [Local readiness check (November 7, 2026)](#local-readiness-check-november-7-2026)
- [Source-only DRAFT publication](#source-only-draft-publication)
- [Release checklist](#release-checklist)
- [Update policy](#update-policy)
- [Repository settings proposal (owner applies)](#repository-settings-proposal-owner-applies)

**Unfinished source-only DRAFT — 0.3.0 unreleased.** This is not a finished product or a cleared binary release.

## CI is not a release certificate

The repository CI installs the locked macOS/Python 3.12 desktop/dev environment and Chrome, then runs the full source suite with isolated synthetic data. It requires no inference credentials, signing secrets or owner Keychain access. Missing optional native CLI probes and explicit signing opt-in tests report their skip reasons. A passed source test does not prove a live account, frozen runtime, native selector, updater installation, notarization or artifact-level license clearance.

Actions are pinned to commit IDs; reverify their upstream provenance when updating them. Workflow permissions are read-only and checkout credentials are not persisted. No pull-request-target, secret-backed untrusted-code path, build artifact upload or automatic release workflow is provided. Logs must not print private runtime state. Browser artifacts remain runner-local; if evidence is later uploaded, allowlist and sanitize it first.

Dependabot is configured for Actions and the supported `uv` ecosystem so both manifest and lock updates are reviewed. Do not auto-merge dependency PRs or treat automation as a binary license audit. Reverify action pins, native dependency notices and account/tool contracts after upgrades.

## Local readiness check (November 7, 2026)

Earlier focused documentation-era verification returned **87 passed, 1 skipped**; it is historical. The pre-upgrade integrated local source checkpoint returned **601 passed, 3 skipped** in approximately 241.1 seconds, including the keyboard duplicate-selection focus regression. The post-upgrade full source run returned **603 passed, 3 skipped, with 2 deprecation warnings in 304.10 seconds**. The updated lock pins AnyIO 4.14.2 and Starlette 1.3.1, covering the seven reviewed advisory patched floors; this is not a whole-project security clearance or confirmation that default-branch GitHub alerts are closed. Native opt-in coverage separately passed **21 tests**. Neither result is hosted CI or frozen positive-selection acceptance. Earlier frozen QA reached the browser/files-only fallback. The source now includes a narrow app-owned WebKit reply bridge compatible with strict CSP. Later QA of the unchanged rebuilt local-preview app opened the real read-only native panel and verified Cancel with no new grants. Positive mixed file/folder selection, returned URLs, context chips, durable grants and revocation remain **BLOCKED by the permitted background input path**, not verified passes or a demonstrated mixed-selection product defect.

The workflow selects `macos-15-intel`. The reviewed portability/navigation repair passed actual hosted CI on November 7, 2026: public run `42392142960` returned **615 passed, 17 skipped, 2 warnings in 558.21 seconds**; private run `42391757389` returned the same counts in **654.73 seconds**. The earlier billing/startup block and 37-failure runs are historical, not current evidence against those repaired heads. Later commits require their own checks. Native-client/signing/Cocoa skips and existing dependency warnings remain visible; hosted source success does not clear binary release gates. See the [roadmap](https://github.com/NewBww/knowledge-hub/blob/main/docs/roadmap.md) for the pending-work index.

## Source-only DRAFT publication

An explicitly unfinished source-only DRAFT may be shared without completing binary acceptance or frozen-payload licensing. Before any public push, review the exact allowlisted bytes for privacy, secrets, authorship/origin and intentional attribution; DRAFT visibility is still public. This documentation does not resolve ownership or legal clearance. Protected-main merge and finished release still require actual green CI, applicable acceptance checks and relevant license gates; no force push or protection bypass is authorized.

## Release checklist

1. Set one approved version in source metadata; align lock metadata, runtime/bundle, release notes, artifact names and eventual tag. Leave pending changes under Unreleased until a real release is established.
2. Complete source privacy/security review, including untracked files. Preserve upstream MIT terms; verify third-party source and frozen native-library obligations separately. Do not rewrite license findings into a clearance claim.
3. Run locked tests, link checks, migration/recovery checks and the real packaged app on each offered architecture. Verify empty install, synthetic persistence, shutdown, MCP, extraction, permissions and any new worker/context capability.
4. Follow [local preparation and release gates](https://github.com/NewBww/knowledge-hub/blob/main/docs/releasing.md). Publisher update signing, Apple code signing/notarization and dependency redistribution clearance are independent. If any required gate is unresolved, stop before public binary publication.
5. Review exact source commit/tag and immutable asset digests. Only an explicitly authorized release owner publishes. Read back the public commit/release/assets and verify downloaded bytes/signatures before claiming delivery.
6. Update canonical docs, changelog, version provenance and Wiki together after verification. Never invent older source snapshots to match historical installers.

## Update policy

Manual native Sparkle checks and human-confirmed installation are implemented paths; automatic checks/downloads/profiling are disabled. The fixed public feed is configuration, not evidence that a live approved release exists. Test actual lower-to-higher installed versions, cancellation, signature rejection, compatibility and retained synthetic data. Builds predating the updater need a manual bootstrap replacement. Failed checks must not silently relax trust or select another provider/feed.

## Repository settings proposal (owner applies)

Enable Issues, Wiki and vulnerability reporting if available; enable Discussions only if the maintainer will moderate it. Use the `tests` CI job as a required check after its first successful hosted run, require PRs and resolved conversations, disallow force pushes/deletion on the default branch and prefer squash merges with branch cleanup. Do not require a second maintainer's approval when only one is available; request independent review when feasible and document exceptions. Do not enable automatic merging or release publishing by default. These are proposals, not claims that remote settings changed.

Dependency ecosystem reference: https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories (checked for `uv` support when this configuration was prepared).
