"""Vendored JavaScript has separate grants from pywebview's BSD license."""
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('holder,name', [('Alex Zaslavsky', 'LICENSE.domJSON.txt'), ('Kyle Simpson', 'LICENSE.native-promise-only.txt')])
def test_vendored_javascript_full_grants_are_indexed(tmp_path, holder, name):
    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    app = tmp_path / 'Example.app'
    app.mkdir()
    destination = tmp_path / 'notices'
    report = module['collect'](app, destination, required_distributions=['pywebview'])
    dist = next(d for d in report['distributions'] if d['name'] == 'pywebview')
    notices = {Path(n['file']).name: n for n in dist['notices']}
    assert name in notices, 'vendored JavaScript full license is missing from supporting notices'
    text = (destination / notices[name]['file']).read_text()
    assert holder in text
    assert 'Permission is hereby granted' in text
    assert not report['release_ready']


def test_unreviewed_webview_version_is_rejected_before_writing(tmp_path, monkeypatch):
    import importlib.metadata as metadata
    from types import SimpleNamespace

    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    real = metadata.distribution('pywebview')
    packager = metadata.distribution('pyinstaller')
    unknown = SimpleNamespace(metadata=real.metadata, files=real.files,
                              locate_file=real.locate_file, version='6.2.2')
    monkeypatch.setattr(module['metadata'], 'distributions', lambda **kwargs: [unknown, packager])
    app = tmp_path / 'Example.app'
    app.mkdir()
    output = tmp_path / 'notices'
    with pytest.raises(module['LicenseError'], match='need review'):
        module['collect'](app, output, required_distributions=['pywebview'])
    assert not output.exists()


def test_vendored_js_identity_mismatch_is_rejected_before_writing(tmp_path, monkeypatch):
    import json

    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    assets = tmp_path / 'assets'
    assets.mkdir()
    entry = json.loads((ROOT / 'assets/licenses/SOURCES.json').read_text())['pywebview']
    entry['installed_files']['webview/js/lib/dom_json.js'] = '0' * 64
    (assets / 'SOURCES.json').write_text(json.dumps({'pywebview': entry}))
    monkeypatch.setitem(module['collect'].__globals__, 'ASSETS', assets)
    app = tmp_path / 'Example.app'
    app.mkdir()
    output = tmp_path / 'notices'
    with pytest.raises(module['LicenseError'], match='source identity mismatch'):
        module['collect'](app, output, required_distributions=['pywebview'])
    assert not output.exists()
