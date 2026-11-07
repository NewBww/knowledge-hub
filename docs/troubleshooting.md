# Troubleshooting and accessibility

| Symptom | Safe next step |
| --- | --- |
| Empty Library | Check Warehouse/Activity. Saved or accepted knowledge need not have an accepted book. |
| Capture stays waiting | Confirm an external agent is actually claiming work, or check managed consent, shared access, readiness and enablement separately. Do not resubmit repeatedly. |
| Context source unavailable/revoked | Inspect the source and current exclusion/ignore policy; use the native picker for a fresh narrow grant if intended. Do not bypass checks with paths or symlinks. |
| Curator job stale or blocked | Inspect the saved reason, source selection and connection consent. Changed content needs a fresh job; retry only eligible work after fixing its cause. |
| Work stops when app quits | Expected: jobs are durable and recover on reopen, not processed by an independent background service. |
| Missing CLI/sign-in required | Follow the Settings instructions for the intended app-owned profile. The app does not install or sign in clients for you. |
| Synthetic check fails | Keep processing disabled. Confirm exact supported client/model and account, then retry with synthetic material; never weaken tool limits to get a green result. |
| ChatGPT/Codex cannot run | Execution is intentionally blocked pending a verified deny-all tool contract. Login guidance is not inference support. |
| Unsupported image/PDF | Images are not OCR-read; scanned PDFs may have no text. Supply a supported text representation or use a separately authorized external workflow. |
| Stale passage/proposal/cursor | Reread current revisions and rebuild context. Keep the draft; do not force approval or combine fragments from different revisions. |
| Update unavailable | Install in a writable location, eject the image, inspect the explicit reason. A source build or absent approved public feed is not an updater success. |
| macOS blocks launch | Verify origin/digest and signing limitations. Do not globally disable platform protections. |
| App opens wrong knowledge | Inspect the chosen data root/environment; do not copy private files into the repository to diagnose. |
| Newer schema or failed migration | Stop and preserve a full backup; use a compatible version. Never manually decrement schema metadata. |
| Duplicate app in search | Eject installer images and inspect actual installed/build copies. Do not reset system indexes or delete the working app blindly. |

## Keyboard and accessible use

- **Command-K / Control-K** focuses the visible Library/Warehouse search when the workspace is available.
- In the capture composer, **Enter** submits; **Shift-Enter** inserts a newline. IME composition is handled separately.
- Standard Tab/Shift-Tab navigation and native form controls support keyboard operation. Visible focus and reduced-motion behavior are part of the design contract.

These are implemented shortcuts, not a claim that every OS-level menu shortcut or assistive technology combination was tested. The desktop uses WebKit-hosted HTML, not native SwiftUI controls. Browser keyboard/responsive tests do not establish VoiceOver certification, full WCAG conformance or equivalent behavior on every display/OS. Report reproducible focus, contrast, zoom or announcement problems with synthetic examples. See [design](../DESIGN.md).

## Report a problem without leaking knowledge

Use the repository bug form for non-sensitive reports: app/source version, macOS/architecture, installation mode, exact steps and a sanitized error. Say whether it reproduces in a fresh synthetic data directory. Do not attach live databases, personal captures, credential profiles, raw logs or screenshots containing knowledge/tokens. Security issues follow [responsible disclosure](../SECURITY.md), not a public issue.

Implementation references: [keyboard handlers](../src/knowledge_hub/web/app.js), [native runtime](../src/knowledge_hub/desktop.py), [connection limits](curator-connections.md).
