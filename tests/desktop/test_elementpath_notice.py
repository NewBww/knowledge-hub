"""The compiled ElementPath implementation retains its own copyright range."""
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]


def test_compiled_elementpath_specific_notice_is_in_supporting_documentation(tmp_path):
    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    app = tmp_path / 'Example.app'
    app.mkdir()
    destination = tmp_path / 'notices'
    report = module['collect'](app, destination, required_distributions=['lxml'])
    lxml = next(d for d in report['distributions'] if d['name'] == 'lxml')
    texts = '\n'.join((destination / n['file']).read_text() for n in lxml['notices'])
    assert 'Copyright (c) 1999-2009 by Fredrik Lundh' in texts, 'older generic ElementTree text does not preserve the compiled source notice'
    assert 'Copyright (c) 2003-2009 by Fredrik Lundh' in texts
    notice = next(n for n in lxml['notices'] if n['file'].endswith('LICENSE.elementpath-header.txt'))
    assert notice['source_member'] == 'lxml-6.1.3/src/lxml/_elementpath.py'
    assert notice['source_sha256'] == '6fcd213379dd0244ed457eafe78cdadcb92402a09c774ef4d016cc3d91e74c15'
    assert not report['release_ready']
