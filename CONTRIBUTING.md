# Contributing with a person or agent

This application is client/provider-neutral. Use whichever coding agent you prefer; do not require the original author's Hermes configuration or private knowledge to change it.

## Orient before editing

1. Read `PRODUCT.md` for product truth and `docs/acceptance.md` for the current milestone boundary.
2. Read `tests/contracts/backend-contract.md` and `docs/agent-collaboration.md` for API, permission and extension rules.
3. For agent retrieval, read `docs/agent-retrieval.md` and the implementation contract when present. A requirement document is not a claim that every capability is implemented.
4. For UI work, read [the reader surface contract](docs/reader-surface.md) and [the design tokens](DESIGN.md). These public documents define the surface without local design-tool state. Preserve the chosen visual direction unless asked to redesign.
5. Inspect relevant tests and the scoped Git diff. Do not copy private workspace data into fixtures or diagnostics.

## Module boundaries

- `core.py`: typed commands and stable domain errors.
- `store.py`: canonical SQLite persistence, revisions and registered dependency invalidation.
- `http.py` and `mcp.py`: transport adapters over the shared application behavior, not separate business logic.
- `web/`: reader/review UI; no SQL or credential persistence.
- `desktop.py`: native WebKit window, local server and clean lifecycle.
- `tools/build_macos.py`: allowlisted bundle staging and architecture-specific distribution.

A connector/provider should enter through a reviewed typed adapter. There is no arbitrary runtime plugin loader. Do not expose shell, SQL, unrestricted files or user-approval flags as agent tools.

## Change and verify

Use incremental RED → GREEN → REFACTOR. Observe a regression fail for the intended missing behavior before changing production code. Test actual HTTP and MCP transport behavior when their contracts change, not only direct Python calls. A real package launch is distinct from a packaging dry-run.

```sh
uv sync --extra desktop --group dev --locked
uv run --locked --extra desktop --group dev playwright install chrome
uv run --locked --extra desktop --group dev pytest -q -rs
uv lock --check
```

Browser tests explicitly launch the Chrome channel; install it with the command above rather than assuming a downloaded Chromium is sufficient. Native desktop/bundle validation requires macOS and the desktop extra. All test knowledge is synthetic and uses isolated temporary data directories. Set `TMPDIR` and pytest `--basetemp` to the approved scratch location when your agent environment specifies one.

Check project isolation, stale revisions, duplicate requests, atomic invalidation, human-only approval, hostile content escaping and explicit failure/omission state. A schema change requires migration and backup/recovery tests before it is called upgrade-safe. No performance or semantic-completeness claims without measurements.

## Public source boundary

Keep credentials, runtime knowledge, captures/originals, local agent/design state, build artifacts and historical development reports out of public source. Ignore rules preserve local files; they are not a publication allowlist. Review and stage explicit paths rather than using `git add .` or `git add -A`, and inspect the staged diff for personal paths, private content and links to excluded material. Historical test totals are not current verification; rerun the documented checks for the revision being released.

## Documentation, community and release gates

Edit canonical documentation before its [Wiki mirror](docs/wiki/README.md). Follow [documentation authority](docs/documentation.md), [security reporting](SECURITY.md) and [maintenance gates](docs/maintenance.md). Keep requested native context/worker work under Unreleased until integrated verification succeeds. CI is read-only and publishes neither packages nor evidence artifacts. Native CLI probes can skip when clients are absent; official Keychain signing tests require explicit local opt-in and must never be enabled in ordinary CI. Report skips, not implied success.

## Finish honestly

Document the changed contract and actual feature limits. Report exact test output and whether the native app, packaged app and MCP connection were exercised. Keep user data outside app/source trees and do not install autostart services, change another user's agent setup or write external systems as part of tests.

Do not commit without approval of the scoped diff and exact message. A push additionally requires approval of the exact target branch. History rewrites require separate explicit approval.
