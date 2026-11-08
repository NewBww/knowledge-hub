<!-- Generated mirror of docs/wiki-maintenance.md; edit canonical source first. -->

# Maintain and publish the Wiki

[Documentation home](https://github.com/NewBww/knowledge-hub/wiki/Home) · [Status and limits](https://github.com/NewBww/knowledge-hub/wiki/Documentation)

**On this page**

- [What lives where](#what-lives-where)
- [Write a useful page](#write-a-useful-page)
- [Regenerate mirrors](#regenerate-mirrors)
- [Validate before publication](#validate-before-publication)
- [Publish the exact reviewed snapshot](#publish-the-exact-reviewed-snapshot)
- [When docs disagree](#when-docs-disagree)
- [Reference](#reference)
- [Next steps](#next-steps)

Keep reader-facing help and developer instructions discoverable without creating a second source of product truth. The Wiki is a separate Git repository; application CI does **not** publish it automatically.

## What lives where

| Content | Authoritative source | Wiki treatment |
| --- | --- | --- |
| Product behavior and procedures | Canonical Markdown in `docs/`, plus `SECURITY.md` | Generated topic mirrors selected by `docs/wiki/sources.json` |
| Entry point and audience navigation | `docs/wiki/Home.md`, `_Sidebar.md`, `_Footer.md` | Explicit versioned navigation assets |
| Current limits and evidence | [Documentation status](https://github.com/NewBww/knowledge-hub/wiki/Documentation) | Link to this page instead of copying volatile totals |
| Build/version identity | `pyproject.toml` and reviewed source/release refs | Never infer a release from a heading or preview filename |

The manifest and `docs/wiki/README.md` are maintainer files, **not** extra reader-facing Wiki pages. Do not copy an entire documentation directory into the Wiki.

## Write a useful page

1. Choose one audience and task. Separate a getting-started procedure from detailed protocol reference.
2. Put prerequisites before commands and an expected result after them. Use locked dependencies, synthetic knowledge and explicit data roots.
3. Use one H1, descriptive H2 sections, numbered procedures and fenced commands. Add short next-step links. Keep stable page names; changing a title is not a reason to break inbound URLs.
4. Explain failure and recovery as well as the happy path. Label local/source, synthetic transport, native acceptance and public-release evidence separately.
5. Use canonical relative links in source. Add a new page to the manifest and grouped sidebar; existing page names stay stable.
6. Never publish personal paths, live knowledge, captures, secrets, private reports or owner screenshots. Do not turn future requirements into supported behavior while copy-editing.

## Regenerate mirrors

Edit the canonical file first. From the source checkout root, run this standard-library script with Python 3.12. It rewrites mapped links to Wiki destinations, repository files/directories to GitHub, and preserves fragments and external links. It does not publish or delete anything.

```sh
python3 - <<'PY'
import json, os, posixpath, re
from pathlib import Path
from urllib.parse import quote, urlsplit

root = Path.cwd()
assert (root / "pyproject.toml").is_file(), "Run from the repository root"
mapping = json.loads((root / "docs/wiki/sources.json").read_text())
wiki = "https://github.com/NewBww/knowledge-hub/wiki/"
repo = "https://github.com/NewBww/knowledge-hub/"
ref = os.environ.get("WIKI_SOURCE_REF", "main")
link_pattern = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)")

def slug(text):
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")

for source, page in mapping.items():
    content = (root / source).read_text()
    def rewrite(match):
        label, target = match.groups()
        url = urlsplit(target)
        if url.scheme or url.netloc or not url.path:
            return match.group(0)
        path = posixpath.normpath(posixpath.join(posixpath.dirname(source), url.path))
        resolved = (root / path).resolve()
        assert resolved.is_relative_to(root.resolve()) and resolved.exists(), path
        if path in mapping:
            destination = wiki + quote(mapping[path])
        else:
            kind = "tree" if resolved.is_dir() else "blob"
            destination = repo + kind + "/" + quote(ref, safe="/") + "/" + quote(path, safe="/")
        if url.query:
            destination += "?" + url.query
        if url.fragment:
            destination += "#" + url.fragment
        return f"[{label}]({destination})"
    rewritten, in_fence = [], False
    for line in content.splitlines(keepends=True):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            rewritten.append(line)
        else:
            rewritten.append(line if in_fence else link_pattern.sub(rewrite, line))
    content = "".join(rewritten)
    headings, in_fence = [], False
    for line in content.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            headings.append(line[3:])
    intro = "[Documentation home](" + wiki + "Home) · [Status and limits](" + wiki + "Documentation)\n\n"
    if len(headings) >= 4:
        intro += "**On this page**\n\n" + "\n".join(
            f"- [{heading}](#{slug(heading)})" for heading in headings
        ) + "\n\n"
    title, rest = content.split("\n", 1)
    generated = f"<!-- Generated mirror of {source}; edit canonical source first. -->\n\n{title}\n\n{intro}{rest.lstrip()}"
    (root / "docs/wiki" / f"{page}.md").write_text(generated)
print(f"Regenerated {len(mapping)} topic pages; Home/sidebar/footer remain explicit sources.")
PY
```

For a source change not yet merged to `main`, set `WIKI_SOURCE_REF` to an **already committed, reviewed SHA containing the linked files** before regeneration. This produces repository permalinks rather than broken links to future `main` content. Commit canonical changes before taking that snapshot. Never use an invented SHA or a moving unreviewed branch as a publication claim.

The generated source comment, breadcrumbs and contents links are mechanical. Do not hand-edit a topic mirror: the next regeneration replaces it. Home/sidebar/footer are edited directly. There is no separately installed Wiki-sync CLI in this repository.

## Validate before publication

- Review the complete diff, including new files. Only documentation should change for a documentation-only update.
- Check all canonical file targets, heading fragments and mapped Wiki destinations. Contents links must match the actual headings.
- Run `git diff --check`. Exercise changed commands safely, and state what was not run: CLI help is not a fresh installation or native-app acceptance.
- Check long-page navigation, code blocks, table readability and the footer in the rendered Wiki, not only local Markdown.
- Review privacy and current status. A historical green run is not a check for this commit; a Wiki update is not binary clearance.
- Follow [Contributing](https://github.com/NewBww/knowledge-hub/blob/main/CONTRIBUTING.md) and protected-branch checks for source integration. Source PR state and Wiki publication are reported separately.

## Publish the exact reviewed snapshot

1. Commit and review canonical docs, navigation, manifest and regenerated mirrors. Record the exact source SHA. Prefer integrated source; if a source PR is pending, state that explicitly and use valid reviewed permalinks.
2. In a separate Wiki checkout, inspect local changes, fetch and fast-forward before editing. If the repository has never been initialized, its owner must create and save Home once through GitHub.
3. Read `docs/wiki/` from the **committed source snapshot**, not an uncommitted working tree. The explicit publication set is the manifest's mapped page names plus `Home.md`, `_Sidebar.md` and `_Footer.md`.
4. Copy only that set. Preserve unrelated owner pages and history. Stage explicit paths, inspect the staged diff and push normally to the Wiki's actual tracking branch.
5. Fetch the exact remote Wiki ref and compare every published file with the selected source bytes. Open Home, the developer quickstart and navigation links in the live renderer.
6. Report what is live, the source revision/PR state, checks and remaining limitations. Do not claim source merged or release-ready merely because the Wiki push succeeded.

## When docs disagree

Prefer implemented contracts and their current tests for behavior, [Product](https://github.com/NewBww/knowledge-hub/blob/main/PRODUCT.md) for intent, [documentation status](https://github.com/NewBww/knowledge-hub/wiki/Documentation) for known limits, and the version manifest for version identity. Retained historical contracts are evidence, not active integration instructions. Fix the canonical page, then regenerate its mirror; do not patch only the rendered Wiki.

## Reference

GitHub's official [Wiki sidebar and footer guidance](https://docs.github.com/en/communities/documenting-your-project-with-wikis/creating-a-footer-or-sidebar-for-your-wiki) documents the native navigation files used here. It is a platform reference, not a claim that these pages publish themselves.

## Next steps

[Documentation authority](https://github.com/NewBww/knowledge-hub/wiki/Documentation) · [Developer quickstart](https://github.com/NewBww/knowledge-hub/wiki/Developer-Quickstart) · [Maintenance and release gates](https://github.com/NewBww/knowledge-hub/wiki/Maintenance) · [Contributing](https://github.com/NewBww/knowledge-hub/blob/main/CONTRIBUTING.md)
