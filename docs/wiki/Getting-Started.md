<!-- Generated mirror of docs/getting-started.md; edit canonical source first. -->

# Getting started

[Documentation home](https://github.com/NewBww/knowledge-hub/wiki/Home) · [Status and limits](https://github.com/NewBww/knowledge-hub/wiki/Documentation)

Use this guide to try the app and understand your first saved capture. For a development environment, targeted tests and contribution workflow, use the [developer quickstart](https://github.com/NewBww/knowledge-hub/wiki/Developer-Quickstart). Reading and search need no model account. See [current status](https://github.com/NewBww/knowledge-hub/wiki/Documentation) before treating a source checkout or local preview as a finished release.

## Packaged app

1. Obtain an explicitly approved candidate from this repository's release page. Do not infer publication or binary clearance from a version mentioned in documentation. Check the release notes for supported architecture and minimum macOS version.
2. Compare the downloaded image against the maintainer's reviewed `SHA256SUMS`, using `shasum -a 256 <downloaded-image.dmg>`. A matching digest checks bytes, not publisher identity. A checksum downloaded from the same compromised location is not independent authentication.
3. Mount the DMG, drag `Knowledge Hub.app` into Applications, eject the image and open the installed copy. Launching from the read-only image can prevent updates.
4. Current packaging is ad-hoc signed, **not Developer ID signed or notarized**. A macOS warning is not a reason to disable Gatekeeper globally or strip quarantine blindly. If your policy requires notarization, stop and use source mode or wait for a compliant release. Report unexpected verification failures privately when sensitive.

The runtime is bundled; recipients do not need Python. A build recipe or local artifact does not imply public redistribution is approved. See [release gates](https://github.com/NewBww/knowledge-hub/blob/main/docs/releasing.md).

## Source installation

Use macOS, Python 3.12 and `uv`. From a checkout:

```sh
uv sync --extra desktop --group dev --locked
uv run --locked --extra desktop --group dev knowledge-hub
```

To keep a trial separate, use `knowledge-hub --data-dir <new-trial-directory>` through the same `uv run` command. The directory is created locally. Do not point tests at the default data root. Source dependency installation accesses public package registries; normal reading does not require inference.

## Your first five minutes

1. An empty installation opens to a capture input; no project or book setup is required.
2. Choose **Add knowledge**, enter a short non-sensitive note and save. This saves a local work item, not an accepted fact and not proof a model ran.
3. Open Activity to inspect its state and attachments. Use your own connected agent or configure the optional Curator in Settings. Explicitly approve any data disclosure before processing.
4. Review the resulting pending change: compare before/after, evidence and affected knowledge. Accept only if supported, or reject it. Agents cannot accept on your behalf.
5. Read accepted knowledge in Warehouse. A Library book appears only after a reading-surface proposal is separately accepted; an empty Library with existing knowledge is valid.

Use **Request something** for an explanation or proposed change. Selected-passage requests preserve the original page/section revision; they do not themselves change knowledge. The bounded managed text worker does not establish support for all request types—use the external-agent workflow when a request is unsupported.

Next: [the user guide](https://github.com/NewBww/knowledge-hub/wiki/Reading-and-Review), [permissions and retention](https://github.com/NewBww/knowledge-hub/wiki/Privacy-and-Context), [backup](https://github.com/NewBww/knowledge-hub/wiki/Backup-and-Migration).
