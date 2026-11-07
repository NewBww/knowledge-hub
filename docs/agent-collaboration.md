# Working with your own agent

> **Historical architecture note:** the external-agent-only runner and file/folder intake descriptions below record an earlier design, not the current complete adapter/picker contract. Current behavior is specified in [agent bootstrap](agent-bootstrap.md), the [Curator contract](curator-contract.md), and [documentation status](documentation.md). Files attach; folders grant scoped read-only access, not recursive upload. Local adapter execution does not confer human approval or provider-disclosure consent.

Knowledge Hub must be usable and maintainable with each owner's preferred agent and model setup. It must not depend on the creator's Hermes profile, subscriptions, credentials or private knowledge.

## Two different agent jobs

### Work with knowledge

Connect an MCP-compatible client to the app's stdio server. Discover tool schemas and capabilities rather than guessing input fields. Reading, search, context retrieval and structured proposals use the same application service as the human UI. The owner reviews accepted changes in the desktop app; an agent cannot self-grant human approval.

Each installation owns its local knowledge. The harness keeps its own models, credentials and source connectors; Knowledge Hub does not ask users to configure them again or embed a replacement AI runner. Basic reading/search do not require a model subscription. A client's model usage and retention policy remain that client's responsibility; a locally installed client may still send selected content to a cloud model, and Hub cannot enforce that provider's behavior after disclosure.

## Two intake routes, one knowledge pipeline

1. **Capture in the app:** paste text, images or selected files/folders into one input. Store a local pending task; the user's connected agent discovers it, retrieves only relevant bounded content and submits evidence-backed proposals. Without an agent, the app honestly shows awaiting-agent rather than pretending it curated the capture.
2. **Feed through MCP:** an agent working in its existing harness can decide when it has durable facts/findings worth keeping, search for existing knowledge and submit a proposal directly. Creating a capture or copying a conversation transcript first is unnecessary.

Both routes converge on the same scoped, revisioned, idempotent proposal/review rules. The Curator is the agent's role, not a separate provider integration. Source connectors, scheduling and model choices stay in the harness. Stable knowledge is maintained; transient captures are cleaned up by their explicit lifecycle instead of becoming a conversation archive. Human approval remains required to change accepted truth.

The packaged executable must support MCP mode directly, without requiring the recipient to install Python or a developer environment. Its command and configuration must be verified against an actual built bundle before the release is called agent-ready.

### Maintain or extend the application

Work in a source checkout, not inside an installed app bundle. Begin with `PRODUCT.md`, `docs/acceptance.md`, the backend contract and the surface brief for the area being changed. Inspect the relevant tests and module boundary before editing. The source must not require private fixtures, the original author's home directory or authenticated design tooling to run its normal tests.

- Domain/storage and application services own accepted knowledge and revision rules.
- HTTP and MCP expose those services; neither is an independent write implementation.
- The web reader consumes the public API rather than editing SQLite.
- The native shell handles window/server lifetime, not business rules.
- Intake services accept local captures and typed external-agent proposals; they do not call model providers or gain approval authority merely because they run locally.
- Future source/publication adapters must preserve provenance and show failed/out-of-sync work explicitly.

Make a narrow change, write and observe a failing regression, implement it and run the complete affected contract suite. A new accepted mutation must preserve project isolation, optimistic concurrency, idempotency, atomic invalidation and the human approval boundary across every transport. Document schema/capability changes and migration/backup implications.

## Extension policy

An extension point is a documented boundary, not a promise that a plugin loader already exists. Knowledge Hub does not dynamically execute downloaded plugins or arbitrary agent-supplied code. Model/provider/source connectors belong in the user's harness, not a duplicate Hub connector catalog. Knowledge-side adapters must use typed inputs, bounded permissions and fixture tests. No arbitrary SQL, shell or unrestricted filesystem tools belong in the knowledge MCP API.

MCP clients may differ, but the behavioral contract must not. Advertise the actual supported feature set and version; unsupported ingestion, automatic publishing or automatic updates must remain explicit rather than stubbed success responses.

## Privacy and upgrades

Keep knowledge outside both the source checkout and application bundle. Ship clean, empty installations. Application replacement must preserve user data; schema changes require a tested migration and backup/recovery story. Private project content and credentials must never be embedded in tests, screenshots, issue reports or release artifacts.
