<!-- Generated mirror of docs/developer-quickstart.md; edit canonical source first. -->

# Developer quickstart

[Documentation home](https://github.com/NewBww/knowledge-hub/wiki/Home) · [Status and limits](https://github.com/NewBww/knowledge-hub/wiki/Documentation)

**On this page**

- [Before you begin](#before-you-begin)
- [1. Clone and install the locked environment](#1-clone-and-install-the-locked-environment)
- [2. Run with disposable knowledge](#2-run-with-disposable-knowledge)
- [3. Run tests](#3-run-tests)
- [4. Make a focused change](#4-make-a-focused-change)
- [Common setup failures](#common-setup-failures)
- [Next steps](#next-steps)

Go from a clean checkout to an isolated development run and a useful test loop. Reading, local search and normal source tests need no inference account. This guide targets macOS and Python 3.12; native packaging currently targets arm64, while hosted source CI runs on macOS Intel.

## Before you begin

- Install Git, Python 3.12 and `uv` through your normal trusted tooling.
- Use synthetic knowledge and a new data directory. Never use your live knowledge store for a test.
- Browser tests use the **Chrome channel**, not just Playwright's Chromium download.
- No Apple Developer membership is required to develop and run locally. Local-preview packaging, trusted distribution and binary redistribution clearance are separate concerns; see [maintenance](https://github.com/NewBww/knowledge-hub/wiki/Maintenance).

## 1. Clone and install the locked environment

```sh
git clone https://github.com/NewBww/knowledge-hub.git
cd knowledge-hub
uv sync --locked --extra desktop --group dev
```

**Expected:** dependencies resolve from `uv.lock` and the project environment is created. Do not run an unreviewed dependency upgrade to repair a setup problem.

## 2. Run with disposable knowledge

```sh
TRIAL_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/knowledge-hub-trial.XXXXXX")"
uv run --locked --extra desktop --group dev knowledge-hub desktop --data-dir "$TRIAL_ROOT"
```

If your environment has an approved scratch directory, set `TMPDIR` to it first. Keep the terminal's `TRIAL_ROOT` value while inspecting that run. The directory is not deleted automatically.

**Expected:** the native window opens with empty local knowledge. No provider sign-in or inference is needed. Quit stops the desktop host and its worker; reopening with the same data directory preserves saved work. Do not point this command at the default personal data directory.

To inspect supported commands without launching the app:

```sh
uv run --locked --extra desktop --group dev knowledge-hub --help
```

## 3. Run tests

Install the browser used by the tests once:

```sh
uv run --locked --extra desktop --group dev playwright install chrome
```

Start with the test file for your change:

```sh
uv run --locked --extra desktop --group dev pytest tests/browser/test_approval_navigation.py -q -rs
```

Before submitting, run the complete source gate:

```sh
uv lock --check
node --check src/knowledge_hub/web/app.js
uv run --locked --extra desktop --group dev pytest -q -rs
```

The JavaScript syntax check requires Node.js. For workflow changes also run `actionlint .github/workflows/ci.yml` with actionlint installed. Honor an agent environment's scratch policy by setting `TMPDIR` and pytest `--basetemp`; use a fresh subdirectory per run.

**Expected:** report the actual pass/fail counts, skip reasons and warnings for your commit. Native-client, Keychain and Cocoa tests can require explicit opt-ins; a skip is not a native acceptance pass. Never enable live-account or signing probes just to remove skips.

## 4. Make a focused change

1. Find the owning module and tests in the [code map](https://github.com/NewBww/knowledge-hub/wiki/Code-Map).
2. Reproduce the missing behavior with a failing regression before editing production code.
3. Keep HTTP and MCP on shared services; preserve human-only approval, revisions, idempotency and bounded disclosure.
4. Run affected tests, then the full gate. Keep design, implementation, tests and documentation in the same PR.
5. Update canonical docs and their Wiki mirrors; use the [Wiki maintenance guide](https://github.com/NewBww/knowledge-hub/wiki/Wiki-Maintenance).

Follow [Contributing](https://github.com/NewBww/knowledge-hub/blob/main/CONTRIBUTING.md) for review/publication rules. Do not stage runtime knowledge, credentials, installer output or raw QA evidence.

## Common setup failures

| Symptom | Check first |
| --- | --- |
| Chrome executable missing | Run the Chrome installation command above; browser tests request `channel='chrome'`. |
| Cocoa/WebKit import unavailable | Use macOS and install the `desktop` extra in the same locked environment. |
| A test sees another environment's packages | Inspect the actual interpreter and installed versions; remove inherited `PYTHONPATH`/`PYTHONHOME` before blaming the lock. |
| Unexpected personal knowledge appears | Quit, inspect `--data-dir` and `KNOWLEDGE_HUB_DATA_DIR`, then use a new synthetic directory. |
| Native build refuses Intel | Source CI can run on Intel; current native artifact architecture support is separate. Do not patch the architecture gate. |
| A legacy project route returns 410 | Use shared routes and current MCP discovery, not historical project-scoped examples. |

## Next steps

[Understand the code](https://github.com/NewBww/knowledge-hub/wiki/Code-Map) · [Connect an agent](https://github.com/NewBww/knowledge-hub/wiki/Agent-Setup) · [Check supported connections](https://github.com/NewBww/knowledge-hub/wiki/Connections) · [Report a problem safely](https://github.com/NewBww/knowledge-hub/wiki/Troubleshooting#report-a-problem-without-leaking-knowledge)
