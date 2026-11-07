# macOS desktop and packaging

**Unfinished source-only DRAFT — 0.3.0 unreleased.** This is not a finished product or a cleared binary release.

## Runtime contract

`knowledge_hub.desktop.launch(data_dir: Path | None = None)` must run on the main thread. It reserves an IPv4 socket on **127.0.0.1:0**, starts a non-daemon uvicorn asyncio thread on that exact socket, and waits for HTTP 200 from `/` before creating the native window. Closing the final pywebview window returns from `webview.start`; the context manager requests server shutdown, joins the thread, and closes its socket. Failed readiness and native startup also clean up. There is no browser fallback.

The native boundary is pywebview `create_window(title, url=..., ...)` followed by `start(gui='cocoa', debug=False, private_mode=True)`. Cocoa is imported explicitly first: pywebview's selector otherwise permits a Qt fallback. Upstream API and selector were checked against `webview/__init__.py` and `webview/guilib.py` at https://github.com/r0x0r/pywebview (the installed version must also be exercised during release smoke testing).

The ephemeral human bootstrap credential is placed only in `/#token=...`, never a query parameter or command-line argument. The frontend exchanges it at `POST /api/session` and strips the fragment. Backend session cookies must be HttpOnly and SameSite=Strict. The separate persistent `agent.token` is mode 0600; token reads/writes take an advisory lock, reject symlinks, and never enter the archive. Native diagnostics are disabled while the credential-bearing URL is active; server access logs are disabled. Native failure messages deliberately omit underlying exceptions which might contain that URL.

Data defaults to `platformdirs.user_data_dir('Knowledge Hub', appauthor=False)` (normally `~/Library/Application Support/Knowledge Hub`). Explicit `data_dir` takes precedence over `KNOWLEDGE_HUB_DATA_DIR`. No default path points inside the application or repository. A new runtime directory has an empty database initialized by the backend; the shell does not seed examples. Replacing the app does not touch this directory.

## Native dependency limitation

`tools/build_lxml_macos.py` defaults to validation-only refusal; explicit `--build` constructs an isolated unsigned macOS arm64 candidate in a fresh scratch workspace. This does not install it into the product environment or authorize redistribution. `tools/build_macos.py` accepts the candidate only with all three explicit inputs: `--lxml-candidate-wheel`, `--lxml-candidate-sha256` and `--lxml-candidate-evidence`. It validates bytes/provenance and checks actual freezer selection rather than trusting the import path alone.

The opt-in candidate was integrated into an actual local QA app. `--local-preview` records unresolved blockers for isolated testing; it is not a release bypass. Non-preview candidate publication remains blocked pending exact frozen native/license review. Runtime/native notices, `proxy_tools` metadata reconciliation and signing/notarization remain separate gates; preserve [third-party notice requirements](../THIRD_PARTY_NOTICES.md).

## Build

Use macOS and Python 3.12 with the project's locked dependencies. The parent/backend owns dependency declarations; required packages are pywebview with Cocoa/WebKit PyObjC support, PyInstaller, uvicorn, and platformdirs in addition to the backend requirements.

```sh
uv sync --extra desktop --group dev --locked
uv run --extra desktop --group dev python tools/build_macos.py --dry-run
uv run --extra desktop --group dev python tools/build_macos.py --out dist
```

If the project exposes dev as an optional extra, `--extra dev` is equivalent; the current pyproject uses a dependency group, not an extra. Do not silently drop desktop dependencies. The UI's `src/knowledge_hub/web/index.html` must exist before packaging.

The build script:

- Copies an allowlist of Python application code and public web assets into isolated staging, not the repository or user data directory. Database files, credentials, Markdown/private documents, caches and symlinks are excluded.
- Invokes PyInstaller with `--onedir --windowed`, explicit Cocoa/uvicorn runtime imports, pywebview collection and web asset inclusion. Python and native dependency binaries are included by PyInstaller; recipients do not need Python.
- Takes version from `pyproject.toml`, writes bundle version/identifier metadata, and names the image `Knowledge-Hub-<version>-macos-<architecture>.dmg` for the current host architecture. Build arm64 on Apple Silicon and x86_64 on an Intel host; this is not a universal build.
- Applies and verifies an **ad-hoc local-test signature**, stages only `Knowledge Hub.app` and an `/Applications` symlink, creates a compressed UDZO image with `hdiutil`, and verifies it. A small version/architecture JSON manifest accompanies the image.
- Keeps PyInstaller's `.app` **and** sibling onedir payload in ephemeral `freeze.noindex` staging beneath a temporary `knowledge-hub-build-*.noindex` directory, not `dist`. The drag-install source is a separate `image.noindex` directory. Normal completion and Python exception unwinding remove that temporary tree. Only the DMG and manifest persist in the output directory; there is no persistent same-named development application. Abrupt process termination can leave scratch staging behind.
- Supplies `assets/macos/KnowledgeHub.icns` through PyInstaller `--icon` and writes `CFBundleIconFile=KnowledgeHub.icns` in the bundle plist before ad-hoc signing. PyInstaller copies that basename into `Contents/Resources`; the actual frozen bundle remains a release verification step.

### Original application icon

`assets/macos/KnowledgeHubIcon.swift` is the original, editable CoreGraphics/AppKit artwork source: an oxblood open book, ivory inset macOS silhouette and a restrained ochre reading ribbon. It uses no emoji, fonts, reference screenshots or downloaded imagery. The 16-point slot omits fine page rules and ribbon for legibility; each standard/Retina slot is rendered directly at its own pixel dimensions, not upscaled from a small raster. Swift is needed only to regenerate the artwork, not by the build script or recipient. Rebuilding the ICNS from the included Swift generator reproduced the existing ICNS bytes exactly; this supports generator-to-resource consistency, not exhaustive authorship or legal proof.

Regenerate on macOS, using your configured scratch directory:

```sh
swift assets/macos/KnowledgeHubIcon.swift "$TMPDIR/KnowledgeHub.iconset"
iconutil -c icns "$TMPDIR/KnowledgeHub.iconset" -o assets/macos/KnowledgeHub.icns
iconutil -c iconset assets/macos/KnowledgeHub.icns -o "$TMPDIR/KnowledgeHub-decoded.iconset"
sips -g pixelWidth -g pixelHeight "$TMPDIR/KnowledgeHub-decoded.iconset/"*.png
```

The checked-in ICNS was genuinely produced with Apple `iconutil`, decoded back with that tool, and checked with `sips`: all ten standard/Retina entries for 16, 32, 128, 256 and 512 points are present (16 through 1024 physical pixels). Packaging tests check ICNS structure and, on macOS, independently decode and validate every PNG dimension. The actual 16px, 32px and 512px artwork was visually inspected. This is an application-icon asset, not a generated application screenshot.

### Application search: evidence and limits

Apple's [Launch Services application-registration documentation](https://developer.apple.com/library/archive/documentation/Carbon/Conceptual/LaunchServicesConcepts/LSCConcepts/LSCConcepts.html) explains that Finder registers applications as it becomes aware of them, including navigating to a containing folder. It also documents `CFBundleIconFile`. Apple's [High Resolution Guidelines: icons](https://developer.apple.com/library/archive/documentation/GraphicsAnimation/Conceptual/HighResolutionOSX/Optimizing/Optimizing.html) specifies the ten iconset entries and `iconutil` conversion. These are primary, archived Apple references; they do **not** guarantee current Launch Services exclusion for `.noindex` folders. Treat the suffix as defense in depth, not a registration prohibition. The substantive fix is no persistent development `.app` in `dist`, with temporary staging removed after packaging. No Launch Services registration call is made by the builder.

Read-only inspection on November 4, 2026 found Spotlight indexing enabled. `mdfind` returned **both** `/Applications/Knowledge Hub.app` and the old repository `dist/Knowledge Hub.app`; `lsregister -dump` contained those two paths **and** `/Volumes/Knowledge Hub/Knowledge Hub.app`. Thus the reported duplicate was reproduced in actual metadata, not inferred from filenames. Mounted installer images can expose another real app until ejected. This change does not modify the installed working app, unmount volumes, purge old build output or reset either metadata database.

A new full build was deliberately deferred while backend owners were editing. Consequently disappearance from Spotlight/Launch Services and the visible app-search UI has **not** been verified after a release build. Existing legacy `dist/Knowledge Hub.app` and `dist/Knowledge Hub/` require deliberate release-owner cleanup/quarantine after preserving the installed working version; this script will not silently delete prior outputs. Merely adding `.noindex` does not promise removal of an already registered entry. Do not use global Spotlight/Launch Services resets or privileged commands to hide duplicates.

Read-only checks for the release owner, after packaging, legacy-output handling and ejecting the installer:

```sh
mdfind 'kMDItemContentType == "com.apple.application-bundle" && kMDItemFSName == "Knowledge Hub.app"'
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -dump
```

Confirm the installed path remains valid, no current temporary staging paths exist, and visible application search resolves to the installed copy. Search caches can lag; distinguish indexed paths, Launch Services records and visible search behavior rather than claiming they are equivalent.

This is a repeatable build recipe, not a byte-for-byte reproducibility claim. Dependency versions are locked by uv; Apple tooling and signing timestamps can still change output bytes. Developer ID signing and notarization are not implemented. Manual native Sparkle updater integration exists in source; automatic checks/downloads are disabled, and public feed/release publication and packaged upgrade acceptance remain separate gates. See [releasing](releasing.md). Ad-hoc signing does not satisfy Gatekeeper's distributed-app trust requirements. Do not label these artifacts signed/notarized for public distribution.

## Installation and upgrades

Mount the DMG, drag the app to Applications, unmount the image, and open the installed copy. A first installation must show an empty Library and local capture input, with no project-selection step. For an update, quit the previous app and replace only the `.app`; leave Application Support intact. Back up the data directory before upgrades. Uninstalling the `.app` intentionally does not delete knowledge or credentials.

## Current isolated preview verification

A real 0.3.0 local-preview build was exercised on November 7, 2026 with synthetic data: frozen loopback serving and health, Chrome session bootstrap/cookie protection, human review/approval, restart persistence, 390px no-overflow layout, Unicode DOCX worker extraction and owned-process/listener cleanup passed. The preview included the opt-in lxml candidate. This is stronger than a dry run but narrower than complete installed desktop acceptance.

Earlier frozen QA reached the browser/files-only fallback. The source now includes a narrow app-owned WebKit reply bridge compatible with strict CSP. Later QA of the unchanged rebuilt local-preview app opened the real read-only native panel and verified Cancel with no new grants. Positive mixed file/folder selection, returned URLs, context chips, durable grants and revocation remain **BLOCKED by the permitted background input path**, not verified passes or a demonstrated mixed-selection product defect. Installed updater transitions, full native/runtime license reconciliation, Developer ID signing and notarization remain open. The ad-hoc local-test artifact is not public-release-cleared. Historical observations below remain historical, not claims that the current preview repeated each one.

## TDD evidence

The observations and totals below are historical development evidence, not verification of the current revision. Machine-specific scratch locations are omitted; command examples assume `TMPDIR` is already set to an approved local scratch directory. Rerun the release checklist for every release candidate.

The desktop tests use real sockets, real uvicorn threads, real HTTP and the real backend app; only the native pywebview boundary is substituted. Packaging tests exercise real file staging, metadata generation, command construction, CLI help and Applications symlink creation without pretending that an archive build has run.

Incremental RED → GREEN observations:

1. Runtime/token test failed with missing `knowledge_hub.desktop`; helpers made it pass.
2. HTTP lifecycle test failed with missing `LocalServer`; loopback server and deterministic teardown made it pass.
3. Main-thread test failed because `launch` was missing; launcher guard made it pass.
4. Native-unavailable test failed because no error was raised; explicit dependency error made it pass.
5. Native launcher integration test failed because no window/start calls occurred; full launch path was then implemented and passed against the actual backend/static routes once available.
6. Packaging metadata/staging test failed because the script was absent; allowlisted staging and project-derived metadata made it pass.
7. Windowed/onedir configuration test failed because the command builder was absent; native runtime/assets plan made it pass.
8. Image preparation tests failed because preparation was absent; isolated entrypoint and drag-install staging made them pass.
9. CLI test failed with empty `--help` output; executable CLI made it pass.
10. Cocoa-only test failed by reaching server readiness instead of refusing missing Cocoa; explicit native renderer prerequisite made it pass.
11. Credential symlink test failed because the target was read/chmodded; `O_NOFOLLOW` and locked descriptor access made it pass.
12. Cross-adapter credential test found a newline mismatch with the real CLI loader; writing the exact token without a newline made it pass.
13. Invalid-short-token test initially accepted the file; credential validation made it pass without overwriting the invalid value.

Supplemental readiness-timeout cleanup, native-exception redaction/cleanup and fresh-install/relaunch persistence coverage passed on their first run; these are not claimed as RED cycles.

Final local check: `pytest tests/desktop -q` returned **17 passed in 2.06s**; the combined desktop/unit/integration run returned **38 passed in 3.82s**. A real `tools/build_macos.py --dry-run` succeeded and emitted the arm64 0.1.0 PyInstaller/DMG plan. No full PyInstaller build or actual native window was run by this subagent; those remain the parent's verification responsibility. The launcher integration test exercised actual `/`, session-cookie and project endpoints through real HTTP, with only native window creation/event-loop entry substituted.

## First-release packaging revision verification (November 4, 2026)

Strict incremental production-behavior cycles were run separately:

1. The staging regression failed because `--distpath` still pointed to the persistent output directory; moving freezer output and image source beneath ephemeral `.noindex` staging made it pass (six packaging tests green at that point).
2. The icon regression failed because `assets/macos/KnowledgeHub.icns` was absent; the authored Swift renderer and real `iconutil` conversion supplied it. The initial test incorrectly expected PNG-style `icp4`/`icp5` chunks; Apple's current tool emitted ARGB `ic04`/`ic05`, so validation was corrected to accept both legitimate encodings, not alter the tool output.
3. The icon wiring regression failed because the PyInstaller command lacked `--icon`; explicit icon selection and bundle plist metadata made it pass.

Supplemental native `iconutil` round-trip/dimension validation, CLI dry-run temporary-tree cleanup and synthetic-freezer-error cleanup passed on first execution. They strengthen verification but are not claimed as additional RED cycles. The freezer-failure test substitutes only the external tool boundary; it does not build a real application.

Historical scoped execution (local scratch assignment omitted): `.venv/bin/python -m pytest tests/desktop -q` returned **23 passed in 2.43s**. A real CLI `--dry-run` emitted an arm64 plan with the checked-in ICNS and ephemeral freezer/image paths; all ten ICNS slots were independently decoded and dimension-checked. No new full app/DMG build, installed-app replacement, metadata reset or visible search-result disappearance is claimed. Release-owner verification remains required.

## Release verification checklist (parent/release owner)

- Run `pytest tests/desktop -q` after backend/static routes are ready.
- Build the real app and DMG (not just `--dry-run`); inspect bundle metadata and verify the image mounts with only the app and Applications link.
- On a fresh synthetic data directory, launch the frozen executable/installed app and confirm a dedicated WebKit window, empty Library/local capture and fragment removal. Confirm closing the window terminates the process/listener.
- Create synthetic knowledge, quit, replace the `.app`, reopen with the same data directory and confirm persistence. Check a second fresh directory still starts empty.
- Search the bundle/image for `agent.token`, SQLite databases and any source/private knowledge. Do not package the test runtime data directory.
- Exercise the installed app on each shipped architecture. Actual window and full build validation are delegated to the parent; configuration tests are not evidence of a built artifact.
