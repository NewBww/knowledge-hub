# Versioned GitHub Wiki source

The live reader/developer Wiki is at https://github.com/NewBww/knowledge-hub/wiki. Canonical Markdown remains authoritative; mapped topic files here are generated mirrors, not an independent documentation fork.

See [Maintain and publish the Wiki](../wiki-maintenance.md) for the executable regeneration recipe, review rules, exact-snapshot publication and remote/rendered verification. Start with [Developer quickstart](../developer-quickstart.md) for an isolated development environment and [Code map](../code-map.md) to locate implementation ownership.

## Publication set

- Topic pages: the values in `sources.json`, each suffixed `.md`.
- Navigation: `Home.md`, `_Sidebar.md`, `_Footer.md`.
- Excluded: this README, the manifest, private notes, raw reports, screenshots, runtime data and installers.

The generator preserves source attribution, adds breadcrumbs and contents navigation to longer pages, rewrites mapped targets to stable Wiki names, and resolves other repository links as files or directories while retaining fragments. Set `WIKI_SOURCE_REF` to a reviewed source commit when a new target is not yet integrated into `main`.

Edit canonical pages first and regenerate; edit Home/sidebar/footer directly. Update mapping and grouped navigation together. Validate local targets, heading fragments and Wiki destinations before publishing. No CI workflow publishes the Wiki or clears a binary release.
