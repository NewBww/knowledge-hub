# macOS preview notices and artifact review

The ad-hoc, non-notarized preview path does not waive redistribution requirements. A notice collector, green source tests, or a valid ad-hoc signature is not publication clearance. The production builder retains its unresolved artifact-selection/native-runtime gates until exact-artifact review supports a separately tested preview preparation policy.

## What the package preserves

- Distribution notices selected through the exact Analysis TOC and installed RECORD ownership, including `PYSOURCE` runtime hooks. Build-only packages are not automatically treated as shipped; runtime hooks can have different licensing from their producer's ordinary build hooks.
- Full upstream license texts, source-specific copyright/permission headers and bundle-relative checksum indexes.
- CPython's main license, pinned native dependency notices, observed incorporated-implementation grants, and the complete versioned upstream additional-notice document. This document is a conservative notice superset, not a claim every listed implementation ships. Application-authored build notes identify runtime packaging changes and the producer source.
- Conservative producer-SBOM Rust notices. Superset coverage is not proof every listed crate is linked.
- pywebview's original BSD text, the separately labelled backport attribution, and source-bound full grants for its vendored JavaScript. The known stock/backport versions share those exact JS inputs; other versions or changed source bytes require review.

Canonical mappings are in `assets/licenses/SOURCES.json`; supporting source/provenance records accompany the assets. Preserve original third-party bytes rather than reformatting them. Narrow Git attributes protect byte-pinned notice files where necessary.

## Deliberately omitted packaging content

`lxml.isoschematron` is excluded from the frozen app. The product does not use that optional module, and its data hook would otherwise collect schema extractors without an established redistribution grant. Exclusion is verified in the actual PYZ and resource tree, while frozen Unicode DOCX extraction is regressed separately. The ordinary XML parser and compiled ElementPath remain supported with their applicable notices.

Installation-only `*.dist-info/direct_url.json` files are removed before notice collection/signing, together with their RECORD rows, because local wheel URLs can disclose build-machine paths. This does not remove full licenses, source-bound public backport provenance, or similarly named non-distribution data. Symlink traversal is rejected, and removed filenames are reported bundle-relatively in build metadata.

## Local-only acceptance

When hosted Actions capacity is unavailable, keep exact source and environment snapshots, commands, JUnit output, warnings/skips, mounted inventories and artifact hashes locally. Do not report local execution as hosted CI success or silently change protected-branch settings.

The exact candidate still needs:

1. Source/runtime/notice tests with executed counts and skipped capabilities preserved.
2. A real mounted artifact inventory, source/code comparison and notice-hash verification, including bootstrap/PYZ/base-library/native/resource ownership.
3. Actual frozen functional and native UI acceptance, not only source/browser shims or a cancelled file panel.
4. A separately validated non-notarized preview preparation policy, with explicit launch/signing limitations and no trusted stable-appcast claim.
5. Uploaded-asset download and checksum readback before a release is reported complete.

Known gaps must be repaired, excluded safely with regression coverage, or explicitly resolved with authoritative permission. Do not infer that a generic package license replaces source-specific attribution, or that an upstream metadata omission proves a component is absent.
