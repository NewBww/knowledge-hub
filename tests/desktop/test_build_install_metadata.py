"""Installer provenance must not disclose the builder's local filesystem URLs."""
import csv
import io
import json
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_bundle_excludes_direct_install_urls_but_preserves_dependency_provenance(tmp_path):
    module = runpy.run_path(str(ROOT / 'tools/build_macos.py'))
    app = tmp_path / 'Example.app'
    info = app / 'Contents/Resources/example-1.0.dist-info'
    info.mkdir(parents=True)
    direct = info / 'direct_url.json'
    direct.write_text(json.dumps({'url': 'file:///synthetic-builder-private-location/candidate.whl'}))
    provenance = info / 'knowledge_hub_backport.json'
    provenance.write_bytes(b'{"source":"immutable-public-source","release_ready":false}\n')
    license_file = info / 'LICENSE'
    license_file.write_bytes(b'Synthetic complete dependency license\n')
    record = info / 'RECORD'
    record.write_text('example-1.0.dist-info/direct_url.json,sha256=synthetic,123\nexample-1.0.dist-info/LICENSE,sha256=preserved,38\n')
    assert 'sanitize_install_metadata' in module, 'installed direct URLs are still packaged'
    removed = module['sanitize_install_metadata'](app)
    assert removed == ['Contents/Resources/example-1.0.dist-info/direct_url.json']
    assert not direct.exists()
    assert provenance.read_bytes() == b'{"source":"immutable-public-source","release_ready":false}\n'
    assert license_file.read_bytes() == b'Synthetic complete dependency license\n'
    assert list(csv.reader(io.StringIO(record.read_text()))) == [['example-1.0.dist-info/LICENSE', 'sha256=preserved', '38']]


@pytest.mark.parametrize('member', ['direct_url.json', 'RECORD'])
def test_install_metadata_symlinks_fail_without_modifying_external_targets(tmp_path, member):
    module = runpy.run_path(str(ROOT / 'tools/build_macos.py'))
    app = tmp_path / 'Example.app'
    info = app / 'Contents/Resources/example-1.0.dist-info'
    info.mkdir(parents=True)
    (info / 'direct_url.json').write_text('{"url":"file:///synthetic-only"}')
    external = tmp_path / 'outside-app.txt'
    external.write_bytes(b'unchanged synthetic outside file')
    linked = info / member
    if linked.exists():
        linked.unlink()
    linked.symlink_to(external)
    with pytest.raises(ValueError, match='symlink'):
        module['sanitize_install_metadata'](app)
    assert external.read_bytes() == b'unchanged synthetic outside file'
    assert linked.is_symlink()


def test_non_distribution_direct_url_file_is_not_removed(tmp_path):
    module = runpy.run_path(str(ROOT / 'tools/build_macos.py'))
    app = tmp_path / 'Example.app'
    data = app / 'Contents/Resources/source-provenance/direct_url.json'
    data.parent.mkdir(parents=True)
    data.write_bytes(b'{"source":"synthetic retained provenance"}')
    assert module['sanitize_install_metadata'](app) == []
    assert data.read_bytes() == b'{"source":"synthetic retained provenance"}'
