# Agent retrieval contract

This is a product requirement and acceptance contract. Actual endpoint parameters and verified behavior are documented in the implementation contract; a requirement here is not evidence that an endpoint already implements it.

## Store once, serve a bounded projection

SQLite is the transactional canonical store, not an agent prompt format. Store accepted facts/findings with stable IDs, scope, revision, explicit state, evidence references and dependency edges. Do not duplicate the same fact into separate human/agent masters or use conversation archives as the knowledge model.

Agents consume compact typed JSON or a requested deterministic text projection through the application boundary, not database files or an entire Markdown tree. Readable field names and standard protocol schemas are preferable to cryptic compression that costs more reasoning than it saves.

## Progressive retrieval

1. **Orient:** minimal capabilities and project identity/purpose; discover the actual tool schemas and permission boundary.
2. **Find:** project-scoped search returns a bounded ranked list of IDs, titles, states, revisions and short matching snippets. Full bodies and evidence histories are not the default search payload.
3. **Understand:** request a context pack for a query or selected IDs. Include relevant accepted facts, necessary recorded prerequisites, source identifiers and directly relevant unresolved/review-needed warnings. Deduplicate stable IDs before serialization.
4. **Inspect:** fetch a selected record, evidence details or history explicitly. Long records need an explicit continuation or body-range mechanism rather than a silent whole-project expansion.
5. **Refresh:** revision labels let a client recognize changed state. Never reuse a cursor against a different revision/query without detecting the mismatch. Delta retrieval is a possible later optimization, not an implemented promise.

## Budgets and completeness

- Bound serialized response size, including metadata, not just the prose body.
- Use conservative defaults and explicit caller limits; avoid a default unbounded `context_get`.
- Expose the unit of a budget: characters/UTF-8 bytes are measurable; token counts require a named tokenizer/model or an honestly labelled estimate. Protocol framing and client-side rendering may add overhead.
- Report included IDs/count, finite matched total, whether more remains and a stable continuation. Do not imply that a partial page is all knowledge about the question.
- Do not silently split an identifier, route, claim or evidence locator to fit a pack. If one record is too large, expose its ID and an explicit detail/continuation path, and ensure the cursor can make progress.
- Do not spend most of a small budget on repeated project descriptions, boilerplate, tool instructions, source text or historical revisions.
- Ranking is deterministic local retrieval initially. Do not pretend lexical matches prove semantic completeness or introduce a paid model/vector service merely to assemble context.
- An unresolved or invalidated relevant fact cannot be omitted just to make the answer look clean. Preserve its state and expose incomplete coverage when the budget prevents necessary context from fitting.

## Required regression scenarios

- A large synthetic project does not produce a large default search/context response.
- Small, empty, Unicode-heavy and long-identifier inputs obey the declared size unit.
- Relevant prerequisites are deduplicated and bounded; cycles terminate.
- Current facts and relevant needs-review/unresolved states remain distinguishable.
- Pagination has no duplicate/omitted eligible records at a fixed revision; stale cursors are rejected.
- A single oversized record has a usable follow-up and does not trap pagination.
- Agent output does not include unrelated projects, raw input messages, full source archives, approval credentials or hidden state.
- HTTP and real MCP stdio expose equivalent selection and budget semantics. Measure actual wire output so duplicated representations do not defeat the intended bound.

The first implementation may advertise a smaller supported subset. It must state those limits instead of returning fabricated semantic coverage.
