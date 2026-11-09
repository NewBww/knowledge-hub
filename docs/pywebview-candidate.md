# Optional pywebview dependency candidate

The normal project lock remains unchanged. This **opt-in local build candidate** removes the contradictory `proxy_tools` dependency by backporting pywebview's five module properties from an immutable upstream source revision. It is not an upstream release or automatic redistribution clearance.

## Source and licensing

- Base: the exact pywebview 6.2.1 wheel pinned in `uv.lock` (SHA-256 `9d07275f53894ab4d5e2e0e996227193e7187dec276d9b624dccbce029216b46`).
- Backport source: pywebview PR #1872, commit `238c6705ada00ee3d903c78247e71d9bfecbab87`; the PR was unmerged when inspected.
- Local version: **6.2.1+kh.1**, deliberately distinct from upstream 6.2.1.
- Preserved grant: BSD-3-Clause, in `assets/vendor/pywebview/LICENSE`. Original wheel license bytes remain unchanged; the backport's full license is additionally embedded.
- `assets/vendor/pywebview/PROVENANCE.json` binds original and patched initializer hashes and the upstream source identity. Only the `webview/__init__.py` implementation, local version/dependency metadata, provenance, attribution and wheel RECORD change. All other base wheel payload bytes are preserved.

The backport uses module-level `__getattr__` for deprecated attributes and a lazy sequence for screens. Each explicit screen operation uses a current snapshot; compound Python operations such as `list(screens)` can query twice through iteration and length hints. It does not copy proxy_tools implementation code.

## Offline candidate construction

Obtain the wheel at the URL recorded in `PROVENANCE.json` through your usual trusted download process. The builder has no network access and verifies the pinned checksum before creating output:

```bash
python -E -s tools/build_pywebview_candidate.py \
  --wheel /path/to/pywebview-6.2.1-py3-none-any.whl \
  --out /fresh/scratch/candidate
```

It emits a timestamp-normalized wheel and `evidence.json`, both explicitly blocked from automatic publication. Wheel members are sorted, RECORD hashes are rebuilt, and local paths are excluded from embedded provenance. Repeatability is checked with the same input bytes and build runtime; this is not a universal compressor-version reproducibility claim.

## Isolated acceptance environment

Do not replace the owner's normal environment. Create a separate environment from the ordinary lock, then explicitly overlay only this candidate:

```bash
UV_PROJECT_ENVIRONMENT=/scratch/candidate-env uv sync --locked --extra desktop --group dev
uv pip install --python /scratch/candidate-env/bin/python --no-deps \
  /fresh/scratch/candidate/pywebview-6.2.1+kh.1-py3-none-any.whl
```

A later `uv sync` restores the ordinary locked dependency, so verify installed metadata and the exact imported initializer before testing/freezing. Keeping proxy_tools installed in the environment is intentional: final frozen inventory must prove it was not selected, rather than hiding its import through an uninstallation.

Run all source contracts, browser tests and applicable local native tests using the candidate interpreter, with sanitized PYTHONPATH/PYTHONHOME and isolated scratch HOME/data/TMPDIR. Freeze and mount the actual installer; verify the candidate initializer, its local version, preserved provenance/licenses, and absence of proxy_tools from the frozen PYZ and distribution inventory. Then exercise native rendering/bridge/picker behavior and the frozen runtime. Import-only tests cannot clear these gates.

## Local-only validation policy

While hosted Actions capacity is unavailable, retain exact source/environment hashes, executed commands, logs, JUnit reports, test skips and artifact digests locally. Do not label these as hosted-CI success, repeatedly rerun quota-blocked Actions, or weaken protected-branch requirements without explicit approval. Local validation does not waive native acceptance or licensing obligations.

The normal public-build compliance gate and trusted/notarized release tooling remain unchanged.
