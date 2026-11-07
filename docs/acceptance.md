# First vertical slice: acceptance boundary

This document defines checks, not test results. Execution evidence is recorded separately after the implementation runs.

## Included

| Area | Acceptance check |
| --- | --- |
| Desktop | A real dedicated WebKit window loads the local reader; closing it stops its local HTTP server. No browser-only fallback masquerades as desktop success. |
| Installation | A reproducible .app/.dmg build includes Python and runtime dependencies, not private knowledge or credentials. Signing/notarization is reported separately. |
| Clean start | A new data directory has no projects or example knowledge. A user can create a project and add its first topic through a reviewed proposal. |
| Reading | Project navigation, topic selection, supporting evidence and explicit state are readable at normal and narrow window widths. |
| Search | Local SQLite full-text search works without an LLM; unmatched input has a clear empty state. Query characters cannot become SQL or uncontrolled FTS syntax. |
| Proposal | A structured correction previews changes and registered dependent topics before acceptance. Proposing alone cannot alter accepted knowledge. |
| Approval | Only the authenticated human review path accepts/rejects proposals. Agent credentials cannot grant approval with extra request fields. |
| Consistency | Approval atomically advances a project revision and invalidates transitive known dependents. Stale proposals and failed writes leave accepted data unchanged. |
| Isolation | Cross-project identifiers cannot read or alter another project's records. Dependency cycles terminate safely. |
| Authentication | A launch secret establishes a same-origin HttpOnly session; API data is not public merely because the service binds to localhost. Foreign origins/hosts are rejected. |
| MCP | An actual stdio client discovers tools, reads/searches, proposes a change and observes the permission boundary. HTTP and MCP invoke the same application service. |
| Persistence | Restart, supported database backup/restore and duplicate-request handling preserve accepted state. |
| Content safety | User-supplied strings render as text; identifiers are preserved. No raw message archive, default telemetry, external font or model dependency is required to read. |
| Distribution | Runtime knowledge lives outside both repository and .app. Replacing the binary must not replace the data directory. |

## Explicitly not complete in this slice

- General message/file extraction and an LLM-driven ingestion worker.
- A production Hermes adapter, permission-isolated model process or model-retention guarantee.
- Import/cutover of existing project knowledge; the existing workspace stays untouched.
- Confluence/Postman mutation, source polling, external publications or automatic synchronization.
- Automatic app updates, public release hosting, Apple Developer signing/notarization or App Store submission.
- Multi-user/LAN/remote-agent hosting or an OS-wide shortcut.
- A claim that no unknown dependency or outdated source exists anywhere.

## Verification discipline

Use synthetic fixture projects in isolated temporary directories. Browser screenshots must identify synthetic content and must never contain the owner's private knowledge. Test backend behavior, real HTTP, real MCP stdio and browser interaction separately. A packaged launch is a separate check from source-mode launch. Report exact finite test totals from the executed suite, not from stale logs or subagent estimates.

No commits or pushes are authorized by implementation approval. Present the scoped diff and exact proposed commit message for review first.
