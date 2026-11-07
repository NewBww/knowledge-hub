# Third-party notices and binary-release prerequisites

Knowledge Hub's MIT license covers its original code, not third-party code or
native libraries bundled into a macOS application. This document is a source-tree
compliance guide, **not an artifact inventory or legal clearance**. Public binary
release remains blocked until the items below are resolved for the exact artifact.

## Artifact-level collection

Run `tools/collect_licenses.py` with the **same Python environment and installed
wheels used by PyInstaller**, after freezing and before final signing. It accepts
an explicit bundle, fresh destination, exact build Analysis TOC, additional
required distribution names, optional metadata search paths and an explicit
CPython license file. It never labels every installed development package as
shipped and does not infer a runtime inventory from dependency declarations.

```sh
.venv/bin/python tools/collect_licenses.py \
  --bundle "$APP" \
  --destination "$APP/Contents/Resources/ThirdPartyNotices" \
  --analysis-toc "$WORK/build/Knowledge Hub/Analysis-00.toc"
```

`APP` is the frozen `.app`; `WORK` is the exact build's work directory. There is
no shell expansion inside Python subprocess argument lists. For programmatic
integration, import the module and call:

```python
report = collect(
    bundle=app,
    destination=app / 'Contents/Resources/ThirdPartyNotices',
    analysis_toc=work / 'build/Knowledge Hub/Analysis-00.toc',
)
if report['blockers']:
    raise RuntimeError('Binary publication blocked; inspect ThirdPartyNotices/manifest.json')
```

Additional explicitly verified shipped packages can be passed via repeated
`--distribution NAME` / `required_distributions=[...]`. `--site-packages DIR` is
repeatable; it selects metadata, not a different executable/runtime. When using
another runtime's metadata, run its Python as well: the CPython version in the
report is the collector interpreter's version. `--python-license FILE` overrides
only the runtime license input. Do not mix build environments.

Outputs are a linked `THIRD_PARTY_NOTICES.md`, verbatim license files, and
`manifest.json` containing selected distribution versions, selection reasons,
license hashes/provenance, CPython license, bundle-relative native paths, binary
hashes, linked-library basenames, and detected static iconv symbols. There are no
absolute build/home paths in the manifest. Native inspection uses real `otool`
and `nm`; it does not execute bundle binaries. Only Mach-O files are inspected;
this is macOS tooling, not an ELF/PE compliance scanner. Internal bundle symlinks
are not duplicated; external symlinks are rejected. The destination must be fresh
and have no symlink parents; resolve platform scratch aliases before calling.

A missing required distribution, missing/empty license, changed pinned supplement,
failed native inspection, or unsafe input fails before notice output. Names and
license paths from installed RECORD metadata are preserved, including vendored
notices, without flattening collisions. Development-only packages appear only if
actually selected by build TOC ownership or explicitly requested. TOC selection
uses exact installed RECORD file ownership, not top-level-name guessing. The TOC
must belong to this exact app/build; manual reconciliation is still mandatory,
particularly for vendoring, generated files, native frameworks and unowned files.

The CLI returns **2** while release prerequisites remain. The Python API returns
the blocked report so an orchestrator can inspect it, and raises `LicenseError`
for missing required notices. **Always check `report['blockers']`.** The current
tool intentionally never issues automatic legal clearance (`release_ready` is
false); there is no bypass/approval flag. It can produce notices for local QA,
but must not be interpreted as permission to publish the binary. Copy the complete
notice directory with the app, not just this repository guide, then sign the final
contents. Native hashes describe the inspected pre-signing bytes; retain/reconcile
a post-signing inventory externally if signing changes those bytes.

## Verified native finding: lxml contains static GNU libiconv

The installed lxml **6.1.3** universal2 `etree` extension was inspected directly.
`otool -L` listed only Apple's `libSystem.B.dylib` for both architectures, while
`nm -a` showed **defined** `_libiconv_open`, `_libiconv_close`, and
`__libiconv_version` symbols. This is not a dynamic reference to Apple's system
iconv. Reading the exported version value from the installed extension on the
arm64 host returned **0x0112 = libiconv 1.18**. This host inspection does not prove
the x86_64 slice's version or provenance of a future rebuilt/signed artifact.
The lxml runtime reports libxml2 **2.14.6** and libxslt **1.1.43**.

Exact publicly retrieved source artifacts (archives verified against their
published/build-script SHA-256 values) include:

- [lxml 6.1.3 source](https://files.pythonhosted.org/packages/23/ad/28ecd7cb894d172f3c9c80a075eeeb2017ac62e3632cee05a5f9493547eb/lxml-6.1.3.tar.gz)
  — `45222d94ddd511536f3b2f7d9deae3b2339b4ce0f075f1ca25703b07cad9dd21`.
- [GNU libiconv 1.18 source](https://ftp.gnu.org/pub/gnu/libiconv/libiconv-1.18.tar.gz)
  — `3b08f5f4f9b4eb82f151a7040bfd6fe6c6fb922efe4b1659c66ea933276965e8`.
- [zlib 1.3.2 source](https://zlib.net/fossils/zlib-1.3.2.tar.gz)
  — `bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16`.
  This is the version named in lxml's source build script, **not a verified version
  extracted from this wheel**; its license is preserved conservatively.

`assets/licenses/lxml/` preserves the full LGPL-2.1 text from libiconv, its
accompanying GPL text, zlib license and ElementTree license. The collector also
copies lxml's installed BSD license and `LICENSES.txt` (including libxml2,
libxslt/libexslt notices). Those wheel notices mention iconv licensing but do not
supply the LGPL text or a relinking kit; collecting them alone is insufficient.

**Blocking prerequisite:** choose and validate an LGPL-2.1 section 6 compliance
route for the actual combined extension. For this static wheel, preserve and make
available the corresponding library source, applicable patches/build scripts,
and the application/extension source or relinkable objects and instructions needed
to rebuild/relink against a modified libiconv. Test that a recipient can actually
perform that replacement and run the app; preserve rights to modify and reverse
engineer for debugging those modifications. A generic download URL, this exact
source URL, an MIT app repository, or LGPL text alone does not establish that
route. If instead replacing the wheel with a build using a suitable shared-library
mechanism, verify replacement works and comply with the applicable LGPL terms.
That is a separately approved dependency/build change, not performed here.
Obtain legal review of the chosen route. Do not claim that public Python sources
alone resolve the existing statically linked wheel's obligations.

## Other required release checks

| Component | Collected / observed | Remaining prerequisite |
| --- | --- | --- |
| CPython 3.12.13 | Full installed runtime `LICENSE.txt`, including PSF/history notices. Installed runtime BUILD is `20260303`. | Trace the actual copied framework, stdlib extensions and native libraries to the python-build-standalone build. Preserve all bundled dependency notices; the PSF text alone is not blanket coverage. Inspect the full build metadata/licenses, not just the install-only runtime. |
| PyInstaller 6.22.3 | Full installed `COPYING.txt`, including GPL, **Bootloader Exception** and runtime-hook terms. | Verify the actual bootloader/runtime components are covered by those terms, preserve Apache/runtime notices, and evaluate any bootloader modifications separately. The exception does not relicense other dependencies. |
| PyObjC 13.0 | Some wheels omit license files. Exact 13.0 sdists supply `License.txt` for core, Security and UniformTypeIdentifiers; preserved with archive URL/member/hash. | Confirm final modules/frameworks. Installed `_objc` and `_machsignals` link Apple's `/usr/lib/libffi.dylib`; no libffi source is bundled by this collector merely because PyObjC's license mentions `libffi-src`. Audit the actual artifact for additional copies. Apple's system frameworks are not automatically redistributed app payloads. |
| certifi 2026.10.23 | Full installed MPL-2.0 text plus exact versioned source URL/hash in generated notices. | Preserve recipients' access to covered-file source under MPL-2.0, including corresponding modified source if changed. Retain a source copy/reliable distribution arrangement; do not assume future URL availability. |
| Pillow 13.0.0 | Installed composite LICENSE includes native dependency texts; generated notices explicitly credit the Independent JPEG Group and FreeType Team. | Reconcile the actual copied dylibs/static codecs with those texts; the installed wheel contains many optional libraries, not every one necessarily ships. |
| cryptography 50.0.2 | Full installed dual Apache/BSD texts. Its installed Rust backend reports OpenSSL **4.0.3**. | Identify the exact linked native/Rust dependencies, applicable OpenSSL license/NOTICE and provenance. cryptography's Python license files alone are not coverage for OpenSSL or the Rust dependency graph. |
| Python SSL | Installed CPython SSL reports OpenSSL **3.5.5**, distinct from cryptography's OpenSSL. | Audit this separately if its extension/libraries ship. Do not use the cryptography version/source as a substitute. |
| proxy_tools 0.1.0 | Wheel and sdist omit a license text and declare MIT. Its installed implementation byte-for-byte matches upstream commit `db43f1e35d4f90a65c5a4d56d9e9af88212ec6e6`; that commit's full **BSD** license is preserved. | Resolve the contradictory upstream/license metadata. Collector checks the installed implementation hash and emits `proxy-tools-license-conflict`; preserving the BSD text is not clearance. |
| Additional native frameworks (including any future Sparkle integration) | Only files present in the explicit bundle are inventoried. | Supply exact framework license/NOTICE, version and embedded dependency provenance before shipping. This work does not inspect or authorize the independent Sparkle spike. |

CPython build provenance starting point:
[exact 20260303 arm64 install-only release](https://github.com/astral-sh/python-build-standalone/releases/download/20260303/cpython-3.12.13%2B20260303-aarch64-apple-darwin-install_only.tar.gz).
The matching full-build release provides additional build metadata; the collector
does not assert that this URL proves the installed runtime's exact checksum.

Exact certifi source (download and checksum verified):
[certifi 2026.10.23](https://files.pythonhosted.org/packages/fd/11/b524cbd9bbdaca58608e4cf4053fd463417549e1959fa8d3aa18319f9555/certifi-2026.10.23.tar.gz)
— `a9895e6e2758b371e0545e321a3a8fd1fcfd9829ada8824a936dfb16aaaf36cd`.

Exact proxy_tools license/source evidence:
[BSD license at immutable commit](https://raw.githubusercontent.com/jtushman/proxy_tools/db43f1e35d4f90a65c5a4d56d9e9af88212ec6e6/LICENSE.txt),
[matching implementation](https://raw.githubusercontent.com/jtushman/proxy_tools/db43f1e35d4f90a65c5a4d56d9e9af88212ec6e6/proxy_tools/__init__.py).
See `assets/licenses/SOURCES.json` for supplemental text and archive hashes.

## Verification boundary

Tests exercise real installed distribution metadata/license files, real installed
lxml Mach-O bytes, real macOS native inspection and the runnable CLI. TOC fixtures
use real installed source paths in PyInstaller's literal TOC shape; they are not a
claim that a new production bundle was built. This task does not build, sign,
notarize, commit, push or publish any artifact. Public release approval remains a
separate decision after exact-artifact compliance and target/commit approval.

## Release-readiness diagnostic checkpoint

The existing `0.3.0` DMG is a **LOCAL PREVIEW, NOT PUBLISHABLE**. Its mounted
notice manifest selects 49 distributions and records 52 native binaries. A fresh
Mach-O walk found no native inventory omissions, but six pre-signing hashes differ
from their final signed bytes. Preserve both inventories; a pre-signing hash must
not be used as if it authenticated the post-signing payload.

`prepare_release.py` now additionally checks the **mounted archive's** bundled
compliance report, Developer ID Application certificate chain, Gatekeeper
acceptance, and stapled app notarization. Missing/unresolved reports and ad-hoc
apps are rejected before update signatures are created. These gates do not grant
legal clearance or provision credentials. The existing opt-in Keychain signing
fixture's unsigned synthetic app no longer qualifies as a publishable artifact.

### CPython upstream evidence now preserved

`assets/licenses/cpython-3.12.13-20260303/` contains 19 verbatim license files,
upstream `PYTHON.json`, and `PROVENANCE.json` with archive/member hashes from the
TLS-downloaded, GitHub-digest-verified official full build. The matching official
archives were checked with these SHA-256 values:

- Full `pgo+lto`: `322f857e0d14dced4be7696f90bcbf15e86b7e4766d849cb4b36350a8e448a0d`.
- Install-only: `2c01f29e9e4ddbd57e0319fedecf1f3e222558fce394a3ed4e39d0f750c11988`.
- Install-only stripped: `377234f346fce41b6d3112b5ead89cb6af2d5596244f9edc1a739065770dde1f`.

The installed runtime's libpython has the stripped archive's size but **not its
byte hash**; its install-name is also rewritten to the local uv runtime path.
Section-level reconciliation is still required; no exact-origin assertion is
made. The full build metadata establishes why a dylib-only walk cannot exclude
CPython's static OpenSSL, bzip2, libffi, mpdecimal, expat, lzma, SQLite or UUID
code: many extension modules are built into libpython. It also names
`licenses/LICENSE.zlib-ng.txt`, which is absent from that full archive. These
candidate texts are not automatically collected into the app yet and do not
clear `native-runtime-review`.

### Decisions and external prerequisites still required

- Retain DOCX extraction: the current implementation uses python-docx/lxml. Simply
  excluding lxml would break a supported feature. `build_lxml_macos.py` now builds
  an opt-in, source-hash-verified native candidate; `build_macos.py` requires its
  wheel checksum and build evidence together and stages it without modifying the
  project environment. The candidate preserves XML, XSLT and Schematron support
  and links macOS system iconv. A local-preview frozen app extracted a synthetic
  Unicode DOCX paragraph and table. This engineering evidence does not clear
  final payload reconciliation or native/runtime licensing obligations; candidate
  publication remains explicitly blocked, and default dependencies are unchanged.
- `proxy_tools` has only version `0.1.0` on PyPI. The public package still declares
  MIT while the matching pinned upstream source includes BSD. No metadata/license
  conflict has been silently waived; obtain corrected upstream provenance or a
  separately approved replacement.
- `security find-identity -v -p codesigning` returned **zero valid identities**.
  The owner must provision a Developer ID Application identity and an approved
  notarization credential profile through Apple's normal tools. Do not send keys,
  passwords, signing exports or notarization secrets in chat.
- Sparkle publisher-key use remains a separate authorization gate. This diagnostic
  did not read/export Keychain keys or perform update signing.

Earlier synthetic frozen-runtime diagnostics used the old mounted preview and
fresh scratch stores: DOCX worker extraction succeeded, `/api/health` returned
version `0.3.0`, and the served UI returned HTTP 200. Those historical checks did
not establish final native-window, migration, MCP or updater acceptance.

On November 7, 2026, a current-source local-preview app/DMG was built with the
opt-in lxml candidate. Its actual frozen executable passed synthetic DOCX,
HTTP/browser human-review and restart-persistence checks. The native window
rendered, but its paperclip opened the browser files-only fallback rather than
the required mixed native picker. This is a failed acceptance gate, not release
clearance. The owned processes/listeners were stopped and the QA image ejected.
Final packaging must follow a stable-tree verification, repaired native-picker
acceptance and the chosen version, using an explicit approved scratch `TMPDIR`.

