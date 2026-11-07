# Version history and provenance

This ledger distinguishes application versions, design revisions, and Git history. A design preview does not establish that its interaction is implemented in the application.

## Repository baseline

The public `NewBww/knowledge-hub` repository starts with the original MIT license commit, `a16544679fd5d629ee85a2538c79d8c0d24b6b6d` (`Initial commit`, November 5, 2026). Preserve this commit and its authorship.

The reviewed source import is committed on public `main` as `b28173e6918671705907e0e1a646c09dfac6a904`, followed by separately reviewed changes. The private development repository has its own ancestry; do not import it into public history. The application declares version `0.3.0`; source publication does not establish a tagged or binary release. Exact release-candidate checks and the [release gates](roadmap.md#initial-030-release-gates) still apply.

## Historical version recovery

Earlier local previews were reported for the following versions. A bounded inventory found installers and build manifests for all four, but no verifiable complete historical source snapshots. The manifests do not link those builds to a source commit or source fingerprint. Do not infer a source snapshot from a version string, installer filename, test count, or build timestamp alone.

| Application version | Historical source status | Tag status |
|---|---|---|
| 0.1.0 | Exact source snapshot not yet verified | Not created |
| 0.2.0 | Exact source snapshot not yet verified | Not created |
| 0.2.1 | Exact source snapshot not yet verified | Not created |
| 0.3.0 | Current local source exists; historical build equivalence not established | Not created |

When an original snapshot is verified, record its source location in the private audit, its content fingerprint, version declarations, dependency lock, associated design where available, and the actual checks run. Public documentation must not expose private absolute paths or imported knowledge.

A reconstructed chronology must say when snapshots were recovered and committed. Do not backdate commits or imply that newly recovered commits were the original development history. If a historical snapshot cannot be verified, retain a documented gap instead of manufacturing a tag or changing the current source's version number to impersonate it.

## Design relationship

The Reading room prototypes are synthetic design references, not the application runtime. Revision 7 is the approved design reference identified by the [documentation status](documentation.md). Approval of the design is not evidence that every interaction is implemented or accepted in the application. Its local query matches, model/connection examples and update checks are simulations, not evidence of live backend capability.

Future application versions keep their corresponding approved design, implementation, tests and release notes in the same feature branch and pull request. Use a design revision identifier inside the release record rather than a parallel design-release lifecycle.

## Release record template

For each verified application version, record:

- Version and exact Git commit.
- Annotated tag and whether the version is a preview or stable release.
- Approved design reference and which portions were implemented.
- Source/dependency provenance and known gaps.
- Verification commands, results and important coverage limits.
- Changes, compatibility/migration notes and known limitations.
- Binary publication status, separately from source publication.

No installer, updater feed or binary release is authorized by the existence of a source tag.
