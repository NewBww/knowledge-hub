# Curator connections (source-runtime preview)

## Current integration and limits

The production `knowledge_hub.http.create_app(...)` registers
`connections_http.register(app, store)` behind the loopback Host/Origin/session
boundary. It exposes `app.state.connections`, `app.state.runtime` and
`app.state.curator_runtime`. Settings uses these production routes; browser tests
must not register an extra fixture adapter to hide missing integration.

Construction/startup does not authenticate or invoke inference. Six destinations
are listed; **five bounded transports are implemented**: OpenRouter, Copilot,
OpenCode, Gemini and Hermes. ChatGPT/Codex sign-in guidance is available, but its
inference remains fail-closed because a verified deny-all tool contract is absent.
Installation, sign-in, catalog capability and readiness are different states.

The runtime resolves `SharedWarehouse(store).scope()` lazily. Existing
`AgentAccess`/`Curator.claim` checks govern shared capture access; enabling the
managed Curator does not silently grant that separate permission. Provider output
can prepare only pending proposals, never approve knowledge, execute commands,
attach invented evidence locators or mutate existing record IDs. Exact source
quotations establish provenance, not truth. Images/unsupported extraction remain
outside the bounded text worker. Explicit requests and contextual existing-record
reconciliation need the external-agent workflow; do not treat sign-in as adding
those capabilities.

Source execution is not packaged acceptance. Frozen worker dispatch, bundled
client discovery, native browser/Keychain behavior and installed-app UI require
separate build/runtime tests. Source spawned-worker wall-time/cancellation checks
do not establish frozen-app behavior. No hard address-space memory cap is claimed.

## Human CLI sign-in handoff

1. In Settings, select the destination and explicit model. Inspect the official
   installation/sign-in guide and request **Sign-in instructions**.
2. Inspect the working directory and copy the complete command block, including
   its first `cd -- ...` line. Run it yourself in a POSIX terminal, in order. The
   app does not launch these commands, install a CLI or authenticate an account.
3. Confirm the intended account/provider/model, disclosure and data-sharing
   consent. Run **Run synthetic connection check**. A successful sign-in is not
   a successful check. Failed checks revoke readiness.
4. Only after a successful check, explicitly **Enable processing**. Shared agent
   capture access remains a separate human permission. Every result still needs
   human review.

The handoff returns `cwd`, shell-quoted `cwd_command`, `steps` and shell-quoted
`display_commands`; Settings renders the full script as inert, selectable text.
The legacy `command` argv describes the official action only: it is **not** a
safe standalone replacement for the environment-qualified display commands.
Every display command starts with `env -i`, a bounded runtime `PATH`, and the
app-owned profile environment. No inherited API keys/tokens are displayed or
forwarded by this handoff. Paths containing spaces, quotes or shell syntax are
quoted, including the executable. Missing clients still receive installation
and isolated-profile instructions, not an authentication/readiness claim.

For application data root `<root>`:

| Destination | Human action | Profile shared with its adapter |
|---|---|---|
| ChatGPT | `codex login` | `HOME=<root>/curator-clients/chatgpt`, `CODEX_HOME=<HOME>/config`; inference blocked |
| Copilot | `copilot login` | `HOME=<root>/cli-auth/copilot`, `COPILOT_HOME=<HOME>/.copilot` |
| OpenCode | `opencode auth login` | `HOME=<root>/cli-auth/opencode`, `XDG_DATA_HOME=<HOME>/data` |
| Gemini | `gemini` (interactive official sign-in) | `HOME=<root>/curator-clients/gemini`, `GEMINI_CLI_HOME=<HOME>/config` |
| Hermes | `hermes portal`, then `hermes proxy start --provider nous --host 127.0.0.1 --port <app-root-specific-port>` | `HOME=<root>/curator-clients/hermes`, `HERMES_HOME=<HOME>/config` |

These table entries are explanatory placeholders; use the fully quoted commands
from Settings, not literal `<root>`/`<HOME>` strings. Hermes connects only through
its Nous subscription pure-inference proxy on loopback, never its tool-enabled
agent API. Keep the proxy available for subsequent checks/processing.

No existing CLI credential files are imported. Profile validation rejects
symlinks in the entire lexical ancestor chain and known profile directories,
including `GEMINI_CLI_HOME=<HOME>/config`, before handoff or Gemini execution.
This rejects a pre-existing redirected account/profile; it is not a claim of
race-proof filesystem confinement for human-run clients.

The application does not read/copy/replay an owner's existing CLI credential
files. Official clients own their sign-in and storage, including any OS credential
store they use. Setting `HOME` is not proof that a client never consults an OS
account store. Copilot's installed login help documents secure-store use and a
plaintext profile fallback when unavailable; inspect the intended account and
client policy. No live sign-in or account-store isolation claim is made here.

## Implemented transport gates

| Destination | Current contract and evidence boundary |
|---|---|
| OpenRouter | Native fixed HTTPS API, exact selected model, strict JSON, no supplied tools; synthetic transport/pending-only readback checks, not live account validation |
| Copilot | Native CLI **1.0.93**, app-owned profile, no real tools in the tested wire catalog, sanitized environment and bounded process; pinned native synthetic loopback probes, not live sign-in |
| OpenCode | Native CLI **1.18.31**, pure mode, global and selected-agent deny-all permissions, matching explicit model/small-model and app-owned auth data; native synthetic loopback probes, not live provider authorization. The `openrouter/...` provider route is rejected (`privacy_route_unsupported`); select the native OpenRouter connection instead |
| Gemini | CLI **0.66.0** only, admin-tier deny-all policy and pinned resolution for `gemini-2.5-flash`/`gemini-2.5-pro`; conflicting machine policies fail closed; other versions/models are rejected |
| Hermes | Nous subscription proxy only, fixed app-root-specific loopback endpoint, exact model and empty tools/tool-choice none; synthetic local HTTP validation does not establish a live Nous subscription |
| ChatGPT | Official isolated Codex login guidance; deny-all tool contract unverified, so inference/check/enable remain blocked even if installed or signed in |

Synthetic native CLI probes restrict egress to their selected loopback test port
and use synthetic stores/data, never owner's credentials. They establish tested
client behavior under that fixture, not vendor/account availability or packaged
runtime readiness. Copilot/OpenCode/Gemini inference rejects other client versions
until reverified; human sign-in guidance alone does not pin or verify a client.

## Consent, destination and retention

Only bounded selected capture text plus task instructions should leave through
the confirmed model connection. Consent must cover the **actual destination**:
OpenRouter and its routed inference provider; GitHub Copilot's service/model;
OpenCode's explicitly selected underlying provider; Google's Gemini service; or
Nous and its underlying provider via the local Hermes proxy. A loopback proxy
still forwards inference remotely. Remote inference may cost money.

OpenRouter requests set `provider.data_collection: "deny"`, `provider.zdr: true`,
`provider.require_parameters: true` and `provider.allow_fallbacks: false`. These
are routing constraints, **not a universal no-retention guarantee**. Review
account privacy/input-output collection settings as well as each provider's
terms. OpenRouter documents safety screening even for ZDR traffic, with possible
flagged-content retention for human review, reporting and legal preservation.
Other safety/legal exceptions and non-content operational/account records must
not be conflated with training opt-out or ZDR routing. If no endpoint satisfies
the constraints, report failure rather than silently relaxing them.

Official CLI clients can retain local task/session traces in the app-owned
profile; external services have their own policies. Human consent must not claim
that clearing local task directories erases all client/provider records. No
credential belongs in knowledge, MCP, logs, screenshots or handoff commands.

## Service and HTTP contract

- `Connections(store, vault=None, discover=None)` uses lazy macOS
  Security/PyObjC app-owned Generic Password items for OpenRouter. Missing support
  fails closed: no plaintext/argv-secret fallback in the app. Tests use synthetic
  vaults, not the owner's Keychain.
- `catalog()` lists capabilities, installation/auth guidance and disclosure;
  `state()` reports connection/model, consent, enablement, status, sanitized error
  and optional non-secret staged proposal.
- `stage({connection, model})` is available to authenticated agents. Commands,
  endpoints, keys and enablement fields are rejected. `confirm(..., consent=True,
  human=True)` requires a human and resets readiness/enablement. Each confirmation
  or OpenRouter key replacement writes a fresh random, non-secret `generation`
  (32 hexadecimal characters); staging preserves it. Pending PKCE is invalidated
  on replacement/reconfirmation and bound to its starting generation, checked
  both before exchange and before credential storage. Runtime diagnostic and
  processing snapshots must compare this generation as well as destination/model/
  consent, so a result for an earlier key cannot mark its replacement checked.
  Whole alias segments `auto`/`default`/`latest` are rejected anywhere in a model
  route (including `openrouter/auto`); explicit names such as `autoencoder-v2`
  are not substring-rejected.
- `start_auth(..., human=True)` returns the human CLI handoff or OpenRouter PKCE
  URL. PKCE uses one-use expiring in-memory state/verifier and a fixed official
  exchange endpoint. Key entry and enablement are human-only, never MCP.
- `check(human=True)` uses synthetic material in a disposable store, checks
  claim/submission and pending readback, verifies zero accepted facts and cleans
  up. Failure revokes readiness. `run_once(human=True)` processes at most one
  capture into a pending proposal; disabling cancels and persists disabled state.

Authenticated inspection: `GET /api/curator/catalog`, `GET /api/curator`.
Human-only writes: `POST /api/curator/config`, `/auth/start`, `/auth/complete`,
`/auth/key`, `/enable`, `/check`, `/run` (all suffixes under `/api/curator`).
Config uses `{configuration:{connection,model},confirm:true,consent:true}` for
human confirmation; omitted/false confirmation stages instead. Enable uses
`{enabled:true|false}`; check/run use `{}`.

`GET /curator-auth/callback` is public only for the state-bound OAuth callback:
cross-site redirects lack the strict API session cookie. It cannot enable work,
never reflects the code/key and consumes a pending human-started state. The
Uvicorn access-log filter removes callback query strings; alternative loggers
must do likewise. Browser/provider history remains outside app control.

## Verification and references

- `tests/test_cli_auth_handoff.py`: production `create_app` auth routes/session,
  exact quoted argv/cwd, app-owned paths, no inherited secret display, consistent
  official command metadata and destination/retention disclosure.
- `tests/test_connections_auth_security.py`: generation rotation, stale PKCE
  invalidation before/after exchange (including separate connection instances),
  route-alias rejection without substring false positives, ancestor/config
  symlink denial and Gemini's no-launch boundary.
- `tests/browser/test_cli_auth_settings.py`: real Chrome/loopback production app,
  all five CLI handoffs rendered completely, Hermes's two steps, ChatGPT blocked,
  processing left disabled. No fixture adapter registration or live sign-in.
- `tests/test_cli_auth.py`, `tests/test_cli_connections.py`,
  `tests/test_connections_runtime.py` and app registration contracts cover the
  complementary adapter, claim, diagnostic and worker boundaries. Consult actual
  run output rather than carrying forward historical whole-suite totals.

Official references (plus pinned installed `login --help`/`auth login --help`):

- https://docs.github.com/copilot/how-tos/copilot-cli
- https://opencode.ai/docs/cli/ and https://opencode.ai/docs/permissions/
- https://geminicli.com/docs/get-started/authentication/
- https://developers.openai.com/codex/cli/
- https://hermes-agent.nousresearch.com/docs/user-guide/features/subscription-proxy
- https://openrouter.ai/docs/guides/overview/auth/oauth
- https://openrouter.ai/docs/guides/privacy/data-collection

No live authentication, live model requests, owner credential reads or packaged
runtime verification are implied by these synthetic/source tests.
