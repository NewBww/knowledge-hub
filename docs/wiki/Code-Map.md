<!-- Generated mirror of docs/code-map.md; edit canonical source first. -->

# Code map and change recipes

[Documentation home](https://github.com/NewBww/knowledge-hub/wiki/Home) · [Status and limits](https://github.com/NewBww/knowledge-hub/wiki/Documentation)

**On this page**

- [Runtime at a glance](#runtime-at-a-glance)
- [Find the owning module](#find-the-owning-module)
- [Recipe: change an HTTP or MCP behavior](#recipe-change-an-http-or-mcp-behavior)
- [Recipe: change the reader](#recipe-change-the-reader)
- [Recipe: change storage or dependencies](#recipe-change-storage-or-dependencies)
- [Contract authority](#contract-authority)
- [Next steps](#next-steps)

Use this map to find the service that owns a behavior before changing a transport or UI. File links lead to source; they are not generated API documentation. The [architecture guide](https://github.com/NewBww/knowledge-hub/wiki/Architecture-and-API) explains the boundaries.

## Runtime at a glance

```text
Desktop WebKit window -> authenticated loopback HTTP -> shared application services
External MCP client  -> bounded stdio tools          -> shared application services
                                                     |-- Warehouse + Library
                                                     |-- captures + pending proposals
                                                     `-- scoped sources + durable jobs
Human review -> accepted canonical changes
```

An agent can propose, not approve. Jobs stop on Quit and recover eligible work on reopen. Local storage and consent to a remote inference destination are different boundaries.

## Find the owning module

| If you are changing… | Start here | Relevant verification |
| --- | --- | --- |
| CLI arguments or data-root selection | [cli.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/cli.py) | CLI/data-directory tests in `tests/` |
| Canonical transactions, revisions, dependencies | [core.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/core.py), [store.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/store.py), [shared.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/shared.py) | Domain/contracts plus stale-revision, idempotency and migration coverage |
| Shared HTTP routes and human sessions | [http.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/http.py), [shared_http.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/shared_http.py) | Real HTTP authentication and permission tests |
| MCP setup and retrieval | [mcp.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/mcp.py), [retrieval.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/retrieval.py) | Initialized stdio SDK tests; actual serialized response budgets |
| Books, pages and support references | [library.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/library.py) | Library revision/support validation and human review |
| Reading, navigation, composer or selection | [app.js](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/web/app.js), [web assets](https://github.com/NewBww/knowledge-hub/tree/main/src/knowledge_hub/web) | `tests/browser/`; keep strict CSP and real HTTP fixtures |
| Captures and parser workers | [intake.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/intake.py), [intake_extractors.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/intake_extractors.py) | Bounded extraction, process interruption and frozen-worker checks |
| Read-only file/folder grants | [context_sources.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/context_sources.py), [native_picker.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/native_picker.py) | Traversal/revocation limits; native selection is a separate opt-in gate |
| Resumable Curator jobs | [curator_jobs.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/curator_jobs.py) | Real process interruption, lease fencing and proposal replay |
| Connections and consent | [connections.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/connections.py), [curator connections](https://github.com/NewBww/knowledge-hub/wiki/Connections) | Synthetic provider/process boundaries; never use owner credentials as fixtures |
| Native host lifecycle | [desktop.py](https://github.com/NewBww/knowledge-hub/blob/main/src/knowledge_hub/desktop.py) | `tests/desktop/` plus actual frozen native acceptance |
| Build notices or release preparation | [build_macos.py](https://github.com/NewBww/knowledge-hub/blob/main/tools/build_macos.py), [collect_licenses.py](https://github.com/NewBww/knowledge-hub/blob/main/tools/collect_licenses.py) | `tests/desktop/`; exact mounted payload and public gate rejection |

## Recipe: change an HTTP or MCP behavior

1. Check the current shared service and discovered MCP input schema. Legacy `/api/projects` HTTP contracts are historical and return 410 in the shared app.
2. Add a regression at the real transport boundary. Exercise invalid/extra fields, human versus agent authority, revision conflicts and repeated requests where applicable.
3. Implement the behavior in the owning service, then adapt the transport. Do not create a second write path or add arbitrary shell/SQL/filesystem tools.
4. Update the current contract, capability discovery and setup guidance together. A source regression does not establish account/provider compatibility.

Reference: [agent bootstrap](https://github.com/NewBww/knowledge-hub/wiki/Agent-Setup), [retrieval](https://github.com/NewBww/knowledge-hub/blob/main/docs/agent-retrieval.md), [Curator contract](https://github.com/NewBww/knowledge-hub/blob/main/docs/curator-contract.md).

## Recipe: change the reader

Read [Design](https://github.com/NewBww/knowledge-hub/blob/main/DESIGN.md) and the [reader surface contract](https://github.com/NewBww/knowledge-hub/blob/main/docs/reader-surface.md). Use synthetic data and a real browser/API flow. Check newer navigation against late responses, keyboard focus, unsaved drafts, narrow layouts and selected-passage revision binding. Keep untrusted content inert; do not weaken CSP to make a test run.

Reference: [reading and review](https://github.com/NewBww/knowledge-hub/wiki/Reading-and-Review), [accessibility limits](https://github.com/NewBww/knowledge-hub/wiki/Troubleshooting#keyboard-and-accessible-use).

## Recipe: change storage or dependencies

Storage changes require supported-version migration, backup/recovery and interruption tests; never hand-edit an owner's database. Dependency changes require review of the whole manifest/lock delta, imported API compatibility and native redistribution implications. Green source CI alone is not binary clearance.

Reference: [backup and migration](https://github.com/NewBww/knowledge-hub/wiki/Backup-and-Migration), [maintenance](https://github.com/NewBww/knowledge-hub/wiki/Maintenance), [release procedure](https://github.com/NewBww/knowledge-hub/blob/main/docs/releasing.md).

## Contract authority

- Version: [pyproject.toml](https://github.com/NewBww/knowledge-hub/blob/main/pyproject.toml).
- Product intent: [Product](https://github.com/NewBww/knowledge-hub/blob/main/PRODUCT.md); delivery index: [roadmap](https://github.com/NewBww/knowledge-hub/blob/main/docs/roadmap.md).
- Current behavior and limits: [documentation status](https://github.com/NewBww/knowledge-hub/wiki/Documentation), source and transport tests.
- Historical designs/contracts are retained as evidence, not instructions to restore retired behavior.

## Next steps

[Run locally](https://github.com/NewBww/knowledge-hub/wiki/Developer-Quickstart) · [Architecture and API](https://github.com/NewBww/knowledge-hub/wiki/Architecture-and-API) · [Maintain the Wiki](https://github.com/NewBww/knowledge-hub/wiki/Wiki-Maintenance) · [Contributing](https://github.com/NewBww/knowledge-hub/blob/main/CONTRIBUTING.md)
