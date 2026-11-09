"""Runtime-hook source entries are redistributed code, not build-only hooks."""
import importlib.metadata as metadata
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_analysis_pysource_selects_runtime_hook_distribution(tmp_path):
    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    dist = metadata.distribution('pyinstaller-hooks-contrib')
    entry = next(p for p in dist.files if str(p).endswith('rthooks/pyi_rth_cryptography_openssl.py'))
    toc = tmp_path / 'Analysis.toc'
    toc.write_text(repr(([], [('pyi_rth_cryptography_openssl', str(dist.locate_file(entry)), 'PYSOURCE')])))
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    output = tmp_path / 'notices'
    report = module['collect'](bundle, output, analysis_toc=toc, required_distributions=['pypdf'])
    names = {d['name'] for d in report['distributions']}
    assert 'pyinstaller-hooks-contrib' in names, 'bundled runtime-hook owner is absent from notices'
    selected = next(d for d in report['distributions'] if d['name'] == 'pyinstaller-hooks-contrib')
    assert selected['selection'] == 'analysis-toc'
    texts = '\n'.join((output / n['file']).read_text() for n in selected['notices'])
    assert 'Runtime hooks' in texts and 'Apache License 2.0' in texts
    assert 'Copyright (c) 2024, PyInstaller Development Team.' in texts, 'compiled runtime hook copyright must be preserved'
    assert report['release_ready'] is False
