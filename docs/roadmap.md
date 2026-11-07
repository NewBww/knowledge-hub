# Roadmap and release backlog

This is the maintained index of pending product and delivery work. Source version **0.3.0 is unreleased**. A requirement, passing source test or approved design is not a shipped feature. Future versions are not numbered until their scope is agreed.

Keep design, implementation, tests, documentation and acceptance evidence together in each change, following the [development workflow](development-workflow.md). [Product](../PRODUCT.md) preserves intent; [documentation status](documentation.md) records verified behavior; [acceptance gates](next-version-acceptance.md) and [release procedure](releasing.md) govern delivery.

## Current baseline

Implemented in source: shared local Warehouse, Library/books and nested reading navigation, local capture, contextual requests, human-reviewed proposals, bounded MCP retrieval, scoped read-only file/folder grants and durable Curator jobs. Jobs stop on Quit and recover eligible work on reopen; they do not run as an independent background service. Live provider accounts, positive frozen mixed-selection acceptance and signed distribution are separate checks.

## Initial 0.3.0 release gates

| Work | Current boundary | Completion evidence needed |
|---|---|---|
| Hosted source verification | CI repair heads passed in both repositories; subsequent commits require their own checks | Green checks on the exact final PR/release candidate, preserving skips and warnings |
| Patched-dependency installer | Earlier preview predates the reviewed AnyIO/Starlette upgrade | Rebuild from the locked candidate; verify frozen runtime, HTTP/browser, extraction, restart and shutdown with synthetic data |
| Native mixed picker | Real panel opening and Cancel verified on an earlier frozen preview; positive selection remains unverified | Actual file plus folder selection, returned context chips, durable grants and revocation in the rebuilt app |
| Binary redistribution | Native/runtime licensing and provenance reconciliation remain open | Exact payload inventory, complete notices and resolution of each recorded blocker |
| macOS trust and updates | Preview uses ad-hoc signing; no trusted distributed release established | Developer ID signing, notarization, Gatekeeper verification and actual signed updater installation/relaunch |
| Human reading/accessibility acceptance | Source/browser checks are not full human acceptance | Nested navigation, phrase-linked review, draft/history recovery, narrow layouts, keyboard and assistive-technology checks |
| Publication | Source availability is not an installer release | Reviewed version/tag, release notes, artifact digests and read-back of exact published assets after all applicable gates |

Do not close a blocked gate by changing the wording, suppressing a test, weakening CSP/permissions, or publishing the local-preview binary. Owner authentication, signing identity provisioning and explicit provider disclosure cannot be fabricated or inferred from general task approval.

## Requested future product work

| Requirement | Scope to preserve | Status / boundary |
|---|---|---|
| Confluence-compatible rich reading and selective publication | Publish selected pages or a book into the user's Confluence space or specified path; design for graphs, tables, images and other supported content | Explicit future requirement in [Product](../PRODUCT.md#future-feature-confluence-compatible-reading-and-selective-publication); adapter, supported variants and fidelity tests not implemented/verified |
| Cross-book knowledge maintenance | Approved factual changes update canonical knowledge and relevant registered reading surfaces with honest work status and recoverable follow-up | Cross-book follow-up/outbox orchestration incomplete; no universal freshness claim |
| Input intent inference | Infer adding knowledge, requesting something, or both from a single input rather than requiring separate intentions | Requested interaction direction; current source still exposes explicit intentions; change requires design/behavior alignment and tests |
| Model effort selection | Let users choose supported reasoning effort with the selected model | Requested direction; compatibility and adapter support require explicit capability checks, not silent provider/model substitution |
| Personal passage formatting | Highlight, bold, underline and strike through selected text for later reading, alongside contextual Ask | Requested reader behavior; do not equate the current selection/Ask toolbar with complete formatting support |
| Comprehensive source-to-book organization | Ingest substantial structured material such as a BMAD archive and propose comprehensive high-level books with nested readable pages | End-to-end organization, evidence coverage, archive limits and review quality require acceptance; bounded attachment ingestion alone is not this feature |
| Phrase-linked collaborative review | Contextual side comments, questions and choices that can be dismissed/reopened and accepted or declined | Partial source interactions do not establish the full requested collaborative workflow |
| Portable knowledge sharing | Deliberately selected knowledge can be shared without bundling the owner's whole store | Future work; privacy, export format and recipient initialization require a separate design |
| Work beyond app lifetime | Continue eligible Curator work across interruption, errors and app closure | Current implementation recovers after reopening only; any independent closed-app worker needs a separate lifecycle/security design |

## Non-goals and invariants

- Canonical knowledge remains on the user's machine. No cloud knowledge database or cloud synchronization roadmap is introduced.
- Optional remote inference and external publication are distinct, explicit disclosure decisions; connecting a provider or granting local folder access does not authorize publication.
- Maintain facts/findings and evidence, not a durable peer-conversation archive.
- External agents cannot approve their own proposals, enable themselves or obtain credentials through MCP.
- Preserve private source material, runtime databases, environments, QA evidence and signing keys outside source publication.

## Repository maintenance queue

- Review dependency and Actions updates individually against pinned contracts, native packaging and applicable migration notes; no unchecked bulk merges.
- Retire merged feature branches only after verifying ancestry or equivalent landed content. Preserve active worktrees, provenance and unmerged work.
- Keep canonical documentation and generated Wiki mirrors aligned. Wiki source files are not evidence that the GitHub Wiki was published.
- Keep private cross-device instructions out of public source; retain independent repository histories and the public upstream license ancestry.
