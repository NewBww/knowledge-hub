# Unified development and release workflow

## One branch for a complete change

Keep design references, implementation, automated checks and documentation together in the same feature/version branch and pull request. Do not create separate application and design branch lifecycles.

- `main`: reviewed integration baseline; no direct publication without explicit authorization.
- `chore/initial-version-history`: prepare the initial source import and truthful history ledger.
- `feat/<change>` or `fix/<change>`: the next complete, narrowly scoped change.

A design can precede implementation inside the branch. Mark it proposed until approved, and distinguish design-only preview behavior from working application functionality. Never advertise a prototype interaction as delivered merely because its HTML is committed.

## Review and commit

1. Inspect the remote, current branch, index and working tree. Preserve the original license history.
2. Build an explicit publication allowlist. Exclude user knowledge, imported originals, databases, credentials, local configuration, agent state, raw local logs, environments and build outputs.
3. Audit source, fixtures, documentation and assets; resolve private paths and sensitive examples without inventing verification results.
4. Run applicable source, browser and packaging checks against a stable snapshot. Record actual results and untested limits.
5. Present the complete scoped diff, exact commit messages, target branch and proposed tag mappings for approval.
6. Commit only approved paths. Recheck the remote/tracking branch after each commit; stop on divergence rather than rewriting history.
7. Push the approved branch and verify its remote object ID. Open a pull request describing design scope, implemented scope, tests and limitations. Verify the PR's head before claiming publication succeeded.
8. Merge only after the required review/checks and authorization. Do not force-push, amend published history or push directly to `main` without explicit approval.

## Version tags

Use annotated application tags such as `v0.3.0` only when the commit represents that exact version and its provenance is verified. Use explicit prerelease identifiers for genuinely new preview versions, without retroactively renaming an old build or making unsupported equivalence claims.

For recovered historical versions:

1. Verify each original source tree, dependency lock and version declaration.
2. Review the exact snapshot and the difference from the preceding verified snapshot.
3. Commit available snapshots in version order, preserving real recovery dates and provenance.
4. Map each annotated tag to its exact reviewed commit.
5. Push explicit branch/tag refs only, then read back both tag objects and their dereferenced commit IDs.

Do not tag every version at the same current commit, fabricate missing intermediate snapshots, backdate commits, overwrite existing tags or publish all local tags indiscriminately. An unavailable version remains a documented gap.

## CI and pull requests

The initial import should establish CI before claiming branch checks are enforced. Add tests and workflow configuration only after verifying the current project commands and dependency constraints. Repository protection is not active until its remote configuration has been read back; do not describe a policy document as an enforced GitHub rule.

Pull request contents should include:

- User-facing behavior and the associated design reference.
- Exact implemented versus proposed scope.
- Test results and coverage limits.
- Privacy/security, migration and compatibility considerations.
- Release/tag intent and any remaining blockers.

## Source versus binary release

Source tags do not authorize an installer release. Binary distribution remains a separate gate for dependency licensing/source obligations, artifact provenance, signing, update validation and notarization where required. Never upload private signing keys or credentials. Keep knowledge storage and private imports outside the repository, application bundle and update traffic.
