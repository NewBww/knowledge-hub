"""Preserve bounded producer-SBOM notices without claiming linked-target clearance."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import runpy

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('name', ['cryptography', 'pydantic-core', 'rpds-py'])
def test_collects_source_bound_native_registry_notices(name, tmp_path):
    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    target = tmp_path / 'notices'
    report = module['collect'](bundle, target, required_distributions=[name])
    selected = next(d for d in report['distributions'] if d['name'] == name)
    notices = [n for n in selected['notices'] if n['file'].startswith('licenses/native-rust/')]
    assert notices, 'producer-SBOM registry notices are not bundled'
    provenance = json.loads((ROOT / 'assets/licenses/native-rust/PROVENANCE.json').read_text())
    expected = {tuple(c[k] for k in ('name', 'version', 'sha256'))
                for c in provenance['components']
                if any(user['package'] == name for user in c['consumers'])}
    assert {(n['component_name'], n['component_version'], n['registry_archive_sha256'])
            for n in notices} == expected
    for notice in notices:
        path = Path(notice['file'])
        assert not path.is_absolute() and '..' not in path.parts
        assert hashlib.sha256((target / path).read_bytes()).hexdigest() == notice['sha256']
        assert notice['coverage'] == 'conservative producer-SBOM registry superset; not linked-target proof'
    installed = metadata.distribution(name)
    source_entry = json.loads((ROOT / 'assets/licenses/SOURCES.json').read_text())[name]
    assert source_entry['version'] == installed.version
    for relative, digest in source_entry['installed_files'].items():
        assert hashlib.sha256(Path(str(installed.locate_file(relative))).read_bytes()).hexdigest() == digest
    assert report['release_ready'] is False
    assert {'artifact-selection-review', 'native-runtime-review'} <= {b['id'] for b in report['blockers']}
    assert str(Path.home()) not in json.dumps(report)


@pytest.mark.parametrize('name', ['cryptography', 'pydantic-core', 'rpds-py'])
@pytest.mark.parametrize('tamper', ['producer-identity', 'notice-bytes'])
def test_existing_native_notice_integrity_checks_fail_closed(name, tamper, tmp_path, monkeypatch):
    """Characterize existing collector enforcement with the new real supplements."""
    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    source = json.loads((ROOT / 'assets/licenses/SOURCES.json').read_text())[name]
    assets = tmp_path / 'assets'
    assets.mkdir()
    if tamper == 'producer-identity':
        source['installed_files'] = {path: '0' * 64 for path in source['installed_files']}
        message = 'supplemental source identity mismatch'
    else:
        source['notices'] = source['notices'][:1]
        corrupted = assets / source['notices'][0]['file']
        corrupted.parent.mkdir(parents=True)
        corrupted.write_bytes(b'corrupted supplemental notice')
        message = 'supplemental notice checksum mismatch'
    (assets / 'SOURCES.json').write_text(json.dumps({name: source}))
    monkeypatch.setitem(module['collect'].__globals__, 'ASSETS', assets)
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    destination = tmp_path / 'notices'
    with pytest.raises(module['LicenseError'], match=message):
        module['collect'](bundle, destination, required_distributions=[name])
    assert not destination.exists()


def test_collects_pinned_cpython_static_component_notices(tmp_path, monkeypatch):
    """Synthetic version fixture exercises collection, not native binary lineage."""
    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    target = tmp_path / 'notices'
    with monkeypatch.context() as scoped:
        scoped.setattr(module['sys'], 'version', '3.12.13 (synthetic notice-collection fixture)')
        report = module['collect'](bundle, target, required_distributions=['pypdf'])
    notices = {Path(n['file']).name: n for n in report['runtime']['notices']}
    expected = {'LICENSE.bzip2.txt', 'LICENSE.libffi.txt', 'LICENSE.mpdecimal.txt',
                'LICENSE.expat.txt', 'LICENSE.openssl-3.txt', 'LICENSE.liblzma.txt',
                'LICENSE.sqlite.txt', 'LICENSE.libuuid.txt'}
    assert expected <= notices.keys(), 'static CPython component notices are not indexed'
    for name in expected:
        notice = notices[name]
        assert hashlib.sha256((target / notice['file']).read_bytes()).hexdigest() == notice['sha256']
        assert notice['coverage'] == 'pinned upstream build notice mapping; not frozen-binary lineage proof'
        assert notice['archive_sha256'] == '322f857e0d14dced4be7696f90bcbf15e86b7e4766d849cb4b36350a8e448a0d'
    assert not report['release_ready']
    assert 'native-runtime-review' in {b['id'] for b in report['blockers']}


@pytest.mark.parametrize('tamper', ['checksum', 'path'])
def test_runtime_notice_tampering_fails_before_output(tamper, tmp_path, monkeypatch):
    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    assets = tmp_path / 'assets'
    assets.mkdir()
    (assets / 'runtime.txt').write_bytes(b'changed runtime notice')
    notice = {'file': '../runtime.txt' if tamper == 'path' else 'runtime.txt', 'sha256': '0' * 64}
    (assets / 'SOURCES.json').write_text(json.dumps({'_runtime': {'3.12.13': [notice]}}))
    monkeypatch.setitem(module['collect'].__globals__, 'ASSETS', assets)
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    target = tmp_path / 'notices'
    message = 'unsafe runtime supplemental notice path' if tamper == 'path' else 'runtime supplemental notice checksum mismatch'
    with monkeypatch.context() as scoped:
        scoped.setattr(module['sys'], 'version', '3.12.13 (synthetic notice-collection fixture)')
        with pytest.raises(module['LicenseError'], match=message):
            module['collect'](bundle, target, required_distributions=['pypdf'])
    assert not target.exists()


def test_runtime_notice_set_does_not_claim_another_version(tmp_path, monkeypatch):
    module = runpy.run_path(str(ROOT / 'tools/collect_licenses.py'))
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    with monkeypatch.context() as scoped:
        scoped.setattr(module['sys'], 'version', '3.12.10 (synthetic notice-collection fixture)')
        report = module['collect'](bundle, tmp_path / 'notices', required_distributions=['pypdf'])
    assert report['runtime']['version'] == '3.12.10'
    assert [n['file'] for n in report['runtime']['notices']] == ['licenses/CPython/LICENSE.txt']
    assert not report['release_ready']
