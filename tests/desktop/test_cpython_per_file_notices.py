"""Version-pinned per-file grants supplement the generic CPython license."""
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('name,holder', [
    ('LICENSE.HACL.txt', 'INRIA, CMU and Microsoft Corporation'),
    ('LICENSE.MersenneTwister.txt', 'Makoto Matsumoto and Takuji Nishimura'),
    ('LICENSE.dtoa.txt', 'Lucent Technologies'),
    ('LICENSE.SipHash.txt', 'Marek Majkowski'),
    ('LICENSE.kqueue.txt', 'Doug White'),
    ('LICENSE.additional-upstream.rst', 'The XML-RPC client interface'),
])
def test_cpython_incorporated_notices_are_indexed_for_the_pinned_runtime(tmp_path, monkeypatch, name, holder):
    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    app = tmp_path / 'Example.app'
    app.mkdir()
    target = tmp_path / 'notices'
    with monkeypatch.context() as scoped:
        scoped.setattr(module['sys'], 'version', '3.12.13 (synthetic notice collector version fixture)')
        report = module['collect'](app, target, required_distributions=['pypdf'])
    indexed = {Path(n['file']).name: n for n in report['runtime']['notices']}
    assert name in indexed, 'embedded CPython implementation notice is missing from documentation'
    notice = indexed[name]
    assert holder in (target / notice['file']).read_text()
    assert notice['source_commit'] == '3bb231a6a5dc02b95658877318bf61501a7209e9'
    assert 'source_sha256' in notice
    assert not report['release_ready']
    assert 'native-runtime-review' in {b['id'] for b in report['blockers']}
