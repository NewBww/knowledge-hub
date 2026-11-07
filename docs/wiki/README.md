# GitHub Wiki source (not published)

Canonical pages live in the main repository. `sources.json` maps canonical paths to Wiki page names; the sibling topic pages are mechanically generated mirrors, not independently handwritten documentation. `Home.md` and `_Sidebar.md` provide explicit GitHub Wiki destinations, which also work when viewed in the source repository.

To regenerate: read each mapped canonical page, prepend the existing generated-source comment, resolve relative Markdown links against the canonical source directory, rewrite mapped targets to explicit `https://github.com/NewBww/knowledge-hub/wiki/<Page>` destinations (preserving fragments), and rewrite other repository targets to the repository's `blob/main/` URL. Leave external URLs and same-page anchors unchanged. Check every mapped page and anchor after regeneration. A release-maintenance generator may implement this contract; none is silently assumed here.

Publish only the mapped topic `.md` files, `Home.md` and `_Sidebar.md` to the separate Wiki checkout after the owner's source/privacy review. Do not copy this manifest/readme, historical reports, raw audits or screenshots into the Wiki. Review the exact Wiki diff and read back rendered navigation after publication. No workflow in this repository publishes the Wiki.

Mirrors reflect current integrated source/context/job documentation. Before publication, refresh after any further integration or version changes; source tests and local-preview checks do not close native-window/picker or release gates. Main-repository links are intended for the approved published default branch, not proof it already contains these files.
