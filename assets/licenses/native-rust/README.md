# Native Rust notice provenance

This directory preserves **270 original notice files for 146 unique registry components** identified by the producer SBOMs of the pinned cryptography, pydantic-core and rpds-py packages. Overlapping components are stored once.

| Producer package | Registry identities matched to its locked source's Cargo.lock |
| --- | ---: |
| cryptography 50.0.2 | 32 |
| pydantic-core 2.50.2 | 101 |
| rpds-py 2026.9.1 | 17 |

## Evidence boundary

`PROVENANCE.json` records exact source-archive and Cargo.lock hashes, producer SBOM hashes/scopes, registry archive identities and individual notice hashes. Package-source identity checks and selected-version mappings are in the parent `SOURCES.json`.

Coverage is deliberately a **conservative producer-SBOM registry superset**. Build helpers and non-macOS targets can be included. Neither `required` scope nor presence here proves a component is linked into a particular native binary. Exact frozen artifact, target/feature, runtime and redistribution review remain separate gates; `release_ready` remains false.

The original producer SBOM hashes document the inspected input wheels. Portable installed-file checks use source-owned package files compared byte-for-byte with the exact locked source archives, not a requirement that unrelated builds reproduce a producer's timestamp/UUID. Those checks are not native binary identity proofs.

## Special source layouts

- r-efi 5.2.0 supplies complete licensing grants and copyright information in `AUTHORS`; it is preserved verbatim, not treated as an author-list substitute for a license.
- wit-bindgen-rt 0.39.0 omits root license files from its registry archive. Its VCS commit/path and exact `src/lib.rs` were reconciled against the immutable upstream tree; the three exact upstream license files and hashes are recorded separately.

All notice text is unchanged. Do not replace copyright/permission/disclaimer text with an SPDX label, edit upstream wording, or treat this collection as a legal-clearance decision.
