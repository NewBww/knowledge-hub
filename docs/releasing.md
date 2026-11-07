# Preparing and releasing Knowledge Hub for macOS

Release preparation is **local only**. `tools/prepare_release.py` never contacts
GitHub, creates tags, commits, pushes, uploads, or publishes a release. A human
must approve the source diff, version, artifact digest and subsequent public
publication. Do not turn model-provided versions or paths into an automated
release job.

## Release contract

- Repository: `https://github.com/NewBww/knowledge-hub` (public, MIT).
- Stable feed: `https://github.com/NewBww/knowledge-hub/releases/latest/download/appcast.xml`.
- Stable versions only: `MAJOR.MINOR.PATCH`, with tag `v<version>`; no leading
  zeroes, prerelease suffixes, build suffixes or arbitrary tag prefixes.
- Archive: `Knowledge-Hub-<version>-macos-arm64.dmg`, with an immutable
  version-tagged enclosure URL under `/releases/download/v<version>/`.
- Feed entries require macOS, `sparkle:hardwareRequirements` of `arm64`, an
  explicit byte length and EdDSA archive signature, and minimum macOS
  `12.0.0` or higher (never lower than the bundle minimum).
- The entire XML feed is also signed by the official Sparkle tool. Its
  `sparkle-signatures` XML comment is part of the signed-feed format; do not
  pretty-print, normalize line endings, append metadata, or edit the signed
  file. Regenerate and re-sign if anything changes.
- Public publisher key: `eRN7w0nSTjTGD/AIwzhAYCE7Ltgm+3yqxlWK1CP11fQ=`.
  This is public configuration, not a credential.

Updates use native Sparkle checks and a human-confirmed, staged installation.
Automatic checking, automatic installation and system profiling are disabled.
The app pins the publisher key, requires signed feeds, sets
`SUSignedFeedFailureExpirationInterval` to `0`, and verifies updates **before
extraction**. The zero interval prevents a permissive unsigned-feed fallback;
it is not a claim that the feed has an authenticated freshness timestamp or
that replay prevention is solved. Compare against the last approved stable
version and test downgrade behavior separately.

**Sparkle EdDSA signatures are not Apple Developer ID signatures.** Current
packaging is ad-hoc signed, not Developer ID signed or notarized. Do not claim
Gatekeeper approval, notarization, or seamless unattended installation. Older
installers built without Sparkle cannot gain self-update support from an
appcast; they require a manual bootstrap installation.

## Prerequisites and key custody

Use an Apple Silicon Mac with Python 3.12+, `uv`, Xcode command-line tools
(`hdiutil`, `lipo`, `codesign`, and `cc` for the optional integration test), and
a trusted **official Sparkle 2.10.1** SDK. Verify the SDK archive against the
pinned URL and SHA-256 in `assets/releases/macos.json` before executing its
binaries; the build tool also validates this distribution. Do not use a
random replacement `sign_update` from `PATH`.

The approved signing key already lives in macOS Keychain under account
`com.knowledgehub.desktop.release`. The preparation tool looks up **only the
public key** using official `generate_keys --account … -p`, checks the pin,
then signs and verifies using official `sign_update --account …`. Keychain
may display a native authorization prompt. Approve access only for the
trusted SDK tool you intentionally invoked; cancellation must block release.

Never export, print, copy into an environment variable, place in a repository,
or pass the private key in a command. Do not create a CI signing secret or a
signing/publishing GitHub Actions workflow. Losing this key is a release
incident: stop and design an authenticated rotation; do not silently replace
the pinned key. These instructions do not authorize any additional key creation.

## Local preparation

Set `SCRATCH` to an approved local scratch directory and `SPARKLE_DIST` to the
verified SDK extraction directory. Examples use variables, not personal paths.
Set `TMPDIR` explicitly so packaging and tests also stay in approved scratch.

```sh
export SCRATCH="<approved-existing-scratch-directory>"
export TMPDIR="$SCRATCH"
export SPARKLE_DIST="<verified-sparkle-distribution-directory>"
uv sync --extra desktop
uv run pytest tests/ --basetemp "$SCRATCH/knowledge-hub-tests"
uv run python tools/build_macos.py \
  --sparkle-distribution "$SPARKLE_DIST" --out "$SCRATCH/build"
```

Before building, review and approve the source version change. Keep project
metadata, bundle versions, artifact name, build manifest, approved source
commit and eventual tag consistent. The preparation tool does not change any
version or infer a new version from a model response.

Independently inspect the DMG and calculate its SHA-256, for example with
`shasum -a 256 <artifact>`. Then supply that **reviewed digest** explicitly:

```sh
uv run python tools/prepare_release.py \
  --version '<approved-version>' \
  --previous-version '<last-approved-stable-version>' \
  --dmg "$SCRATCH/build/Knowledge-Hub-<approved-version>-macos-arm64.dmg" \
  --build-manifest "$SCRATCH/build/Knowledge-Hub-<approved-version>-macos-arm64.build.json" \
  --sha256 '<reviewed-64-character-lowercase-sha256>' \
  --minimum-system-version 12.0.0 \
  --release-notes-text '<reviewed-UTF-8-plain-text-file>' \
  --sparkle-bin "$SPARKLE_DIST/bin" \
  --scratch "$SCRATCH" \
  --output "$SCRATCH/release-<approved-version>"
```

Omit `--previous-version` only for an explicitly reviewed initial release; the
tool does not query GitHub for it. For subsequent releases this argument rejects
equal versions and downgrades. Release notes are optional, serialized as escaped
XML text using Sparkle's **`sparkle:format="plain-text"`**, not HTML or Markdown.
XML control characters and a leading HTTP(S) URL are rejected (Sparkle has a
legacy remote-notes fallback for descriptions beginning with a URL). Do not
add remote release-note links, scripts, active HTML or unsanitized excerpts.

The tool validates the exact build-manifest fields, name, digest and version,
copies a private staging snapshot, verifies and mounts that DMG **read-only**,
then checks the bundle's actual versions, identifier, arm64 executable,
minimum OS, bundled Sparkle presence and strict update policy. It detaches the
mount even if bundle inspection fails. A loose app or a manifest alone is not
evidence of what the DMG contains. Framework presence and plist checks are not
a substitute for the packaged native-update acceptance test below.

Only after official signing and verification does it produce a new output
directory containing:

1. The unchanged, version-named DMG.
2. Signed `appcast.xml` with a single stable entry.
3. `release.json`: public release metadata and signature, with `published: false`
   and `notarized: false`. This describes preparation, not subsequent GitHub state.
4. `SHA256SUMS`: hashes of the above three files, calculated **after** feed signing.

Existing output directories are never overwritten. Failed output copies are
removed. Treat any interrupted run or failed verification as a blocker, not as
a release candidate. Keep `release.json` and `SHA256SUMS` with the candidate for
review; they are public audit metadata, not replacements for pinned-key
signature verification.

## Tests and what they establish

Normal tests never access the owner's Keychain or the network:

```sh
uv run pytest tests/desktop/test_release_feed.py \
  --basetemp "$SCRATCH/release-unit-tests"
```

The real official-tool integration test is opt-in and may prompt for Keychain
access. It builds a **synthetic test-only DMG**, not a Knowledge Hub installer,
uses the approved existing key without exporting it, signs/verifies the archive
and feed, and checks that the official verifier rejects modifications to each:

```sh
KH_SPARKLE_BIN="$SPARKLE_DIST/bin" uv run pytest \
  tests/desktop/test_release_feed.py \
  --basetemp "$SCRATCH/release-signing-tests"
```

Passing this test establishes signing-format interoperability and tamper
rejection, not successful native installation, notarization, network freshness,
GitHub publication, or an end-to-end update of the actual app.

## Human release checklist: review → draft → verify → publish

No publication is authorized merely by running preparation. Obtain separate
approval for the exact public source scope and release assets.

### 1. Review the public source and candidate

- Audit the entire proposed public tree (including untracked files), staged
  diff, generated assets, tests and docs. Exclude all private knowledge stores,
  documents, captures, indexes, logs, local configuration, credentials, personal
  paths and build caches. Packaging must read only public source and assets.
  Inspect the mounted DMG as well; do not assume `.gitignore` is an audit.
- Verify bundled third-party notices and license obligations, including
  Sparkle and transitive packaged dependencies. Do not publish with missing
  notices or substitute a list of package names for license texts.
- Run the full source suite, build and launch the actual packaged app with an
  isolated empty data directory. Verify version, UI, native updater loading,
  permission/cancellation behavior, process shutdown and no knowledge upload.
- Review the scoped diff and exact commit message with the owner. Only after
  explicit approval, commit the approved paths and push the approved `main`
  commit. Do not run blanket `git add .`; do not commit signing scratch output.
- Confirm the eventual `v<version>` tag will identify that exact audited source
  commit. Read back the public GitHub commit/tree after pushing; a local push
  success message alone is not verification.

### 2. Create a draft and verify uploaded bytes

- With explicit publication approval, use the GitHub UI to create a **draft**
  release for the reviewed `v<version>` tag and exact approved commit. Set
  prerelease **off** explicitly. Never publish an unverified draft immediately.
- Upload the prepared DMG and signed `appcast.xml` unchanged. Also upload
  `SHA256SUMS` and `release.json` as public verification records if included in
  the approved asset scope. Never upload build scratch, user data or keys.
- Read back the draft/tag via GitHub. Download its assets into a **different**
  scratch directory through authenticated draft-asset access. Compare their
  lengths and hashes with the locally approved candidate; check all names and
  tag relationships. Verify both downloaded signatures using the official
  tool and the same pinned public-key account. Do not verify local originals
  and describe that as GitHub verification.

For explicit read-back verification, obtain the archive signature from the
reviewed `release.json`; the following commands do not export a key:

```sh
"$SPARKLE_DIST/bin/generate_keys" --account com.knowledgehub.desktop.release -p
"$SPARKLE_DIST/bin/sign_update" --account com.knowledgehub.desktop.release \
  --verify '<downloaded-DMG>' '<reviewed-ed_signature>'
"$SPARKLE_DIST/bin/sign_update" --account com.knowledgehub.desktop.release \
  --verify '<downloaded-appcast.xml>'
```

### 3. Publish only the verified draft; read back the public feed

- After draft asset verification and final approval, publish that exact draft
  as a **stable**, non-prerelease release and explicitly mark it **latest**.
  Do not overwrite or retarget an existing released version.
- Read back GitHub release state (`draft=false`, `prerelease=false`, exact tag,
  exact target commit and assets). Download the anonymous public tagged DMG
  and the **fixed `/releases/latest/download/appcast.xml` URL**, following only
  expected HTTPS GitHub asset redirects. The latest URL must return this
  release's signed feed, not an earlier release or a prerelease.
- Recheck public downloaded bytes, lengths, SHA-256 hashes, feed signature,
  enclosure signature and version-tagged enclosure URL. A release API response
  alone does not prove that the public download path is correct.
- Record the public URLs and verified hashes. Never claim completion if an
  upload, redirect, signature, asset count, or read-back check remains unverified.

### 4. Two-version native update acceptance

Use two real, separately built versions containing Sparkle: install the lower
approved test build in a controlled writable app location, then check against
the higher signed candidate through the native updater. Use isolated synthetic
data; do not replace the owner's running installation or touch private stores.
Verify that checking alone does not install, explicit install confirmation is
required, cancellation leaves the old app intact, a valid archive is staged and
installed by Sparkle, relaunch reports the higher version, and knowledge remains
local. Exercise corrupted archive, invalid/unsigned feed, wrong publisher,
incompatible architecture/OS, equal version and downgrade rejection paths.
Do not weaken the production trust policy or redirect the shipped feed to an
unsigned local server for convenience. A controlled test feed/build needs an
explicitly reviewed test configuration.

This acceptance is a separate release gate. Synthetic signing tests and builds
that predate the native updater do not demonstrate a working two-version update.
If publication has not been approved, stop after local candidate preparation and
report this gate as pending rather than publishing to make a demonstration work.
