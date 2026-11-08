"""Artifact notices use real installed license metadata, not license classifiers."""
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def collector():
    path = ROOT / 'tools/collect_licenses.py'
    assert path.is_file(), 'artifact license collector is not implemented'
    spec = importlib.util.spec_from_file_location('license_collector', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collects_only_explicit_required_installed_distributions(tmp_path):
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    target = tmp_path / 'notices'
    report = module.collect(bundle, target, required_distributions=['pypdf', 'certifi'])
    assert {d['name'] for d in report['distributions']} == {'pypdf', 'certifi', 'pyinstaller'}
    certifi = next(d for d in report['distributions'] if d['name'] == 'certifi')
    source = metadata.distribution('certifi')
    assert certifi['version'] == source.version
    assert certifi['selection'] == 'explicit'
    for notice in certifi['notices']:
        data = (target / notice['file']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == notice['sha256']
        assert b'Mozilla Public License' in data
    assert 'pytest' not in {d['name'] for d in report['distributions']}
    assert (target / 'licenses/CPython/LICENSE.txt').read_bytes()
    assert 'PyInstaller Bootloader Exception' in (target / 'THIRD_PARTY_NOTICES.md').read_text()
    serialized = (target / 'manifest.json').read_text()
    assert str(Path.home()) not in serialized
    assert json.loads(serialized) == report


def test_missing_required_notice_fails_before_writing(tmp_path, monkeypatch):
    import pytest
    module = collector()
    supplements = tmp_path / 'no-supplements'
    supplements.mkdir()
    (supplements / 'SOURCES.json').write_text('{}')
    monkeypatch.setattr(module, 'ASSETS', supplements)
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    destination = tmp_path / 'notices'
    # This real wheel declares MIT but supplies no full license file.
    assert metadata.distribution('proxy_tools').metadata['License'] == 'MIT'
    with pytest.raises(module.LicenseError, match='proxy-tools'):
        module.collect(bundle, destination, required_distributions=['proxy_tools'])
    assert not destination.exists()


def test_native_lxml_inventory_detects_static_iconv_and_blocks_release(tmp_path):
    import shutil
    import sys
    import pytest
    if sys.platform != 'darwin':
        pytest.skip('Mach-O inspection requires macOS tools')
    module = collector()
    dist = metadata.distribution('lxml')
    entry = next(p for p in dist.files if str(p).startswith('lxml/etree.') and str(p).endswith('.so'))
    bundle = tmp_path / 'Example.app'
    native = bundle / 'Contents/Frameworks' / str(entry)
    native.parent.mkdir(parents=True)
    shutil.copyfile(dist.locate_file(entry), native)
    target = tmp_path / 'notices'
    report = module.collect(bundle, target, required_distributions=['lxml'])
    record = report['native_binaries'][0]
    assert record['file'] == native.relative_to(bundle).as_posix()
    assert record['sha256'] == hashlib.sha256(native.read_bytes()).hexdigest()
    assert record['static_iconv_symbols'] is True
    assert record['linked_libraries'] == ['libSystem.B.dylib']
    assert 'lgpl-iconv-relinking' in {b['id'] for b in report['blockers']}
    assert report['release_ready'] is False
    texts = '\n'.join(p.read_text() for p in (target / 'licenses/lxml').rglob('*') if p.is_file())
    assert 'GNU LESSER GENERAL PUBLIC LICENSE' in texts
    assert 'Jean-loup Gailly' in texts
    assert str(Path.home()) not in json.dumps(report)


def test_lxml_special_permission_headers_are_collected_with_exact_provenance(tmp_path):
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    target = tmp_path / 'notices'
    report = module.collect(bundle, target, required_distributions=['lxml', 'proxy_tools'])
    lxml = next(d for d in report['distributions'] if d['name'] == 'lxml')
    notices = {n['file']: n for n in lxml['notices']}
    expected = {
        'dict': ('ea9e97f88bf4ef8ad1142e12d0e6da003968420aa38094f74b9b51206675438a',
                 '416253664eb3d95a393be6c61c649a1b5600729bbd1e3ce9123df08b12d8f388'),
        'list': ('2fdb83809864852d236c64fffa74054699e61887b736e18724d4a8ac0e9684f8',
                 '8a04740bfd8a37f3006bfc0404aa31429e56ef991cddcd47707ce2a9b1d98506'),
    }
    paths = {f'licenses/lxml/libxml2-{name}.c-header.txt' for name in expected}
    assert paths <= notices.keys(), 'exact libxml2 special permission headers must be indexed'
    sources = json.loads((ROOT / 'assets/licenses/SOURCES.json').read_text())['lxml']
    supplements = {n['file']: n for n in sources['notices']}
    index = (target / 'THIRD_PARTY_NOTICES.md').read_text()
    for name, (header_sha, member_sha) in expected.items():
        relative = f'lxml/libxml2-{name}.c-header.txt'
        output = 'licenses/' + relative
        notice = notices[output]
        assert notice == {**supplements[relative], 'file': output}
        data = (ROOT / 'assets/licenses' / relative).read_bytes()
        assert (target / output).read_bytes() == data
        assert hashlib.sha256(data).hexdigest() == notice['sha256'] == header_sha
        assert notice['source_url'] == ('https://download.gnome.org/sources/libxml2/2.15/'
                                        'libxml2-2.15.2.tar.xz')
        assert notice['archive_sha256'] == 'c8b9bc81f8b590c33af8cc6c336dbff2f53409973588a351c95f1c621b13d09d'
        assert notice['source_member'] == f'libxml2-2.15.2/{name}.c'
        assert notice['source_member_sha256'] == member_sha
        assert notice['upstream_commit'] == '3d840e17858de03a09fba8b202e3a89267d5795a'
        assert notice['upstream_url'] == ('https://raw.githubusercontent.com/GNOME/libxml2/'
                                          f"{notice['upstream_commit']}/{name}.c")
        assert notice['extraction'] == 'First /* ... */ comment, including its terminating newline; unchanged bytes.'
        assert f'[{output}]({output})' in index
    assert report['release_ready'] is False
    assert {b['id'] for b in report['blockers']} == {
        'artifact-selection-review', 'native-runtime-review', 'proxy-tools-license-conflict'}
    for dist in report['distributions']:
        for notice in dist['notices']:
            relative = Path(notice['file'])
            assert not relative.is_absolute() and '..' not in relative.parts
            assert hashlib.sha256((target / relative).read_bytes()).hexdigest() == notice['sha256']
    assert json.loads((target / 'manifest.json').read_text()) == report
    assert str(Path.home()) not in json.dumps(report)


def test_lxml_special_permission_header_tampering_fails_before_output(tmp_path, monkeypatch):
    """Characterize existing supplemental checksum enforcement for both new assets."""
    import shutil
    import pytest
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    for name in ('dict', 'list'):
        assets = tmp_path / name / 'assets'
        shutil.copytree(ROOT / 'assets/licenses/lxml', assets / 'lxml')
        shutil.copyfile(ROOT / 'assets/licenses/SOURCES.json', assets / 'SOURCES.json')
        header = assets / f'lxml/libxml2-{name}.c-header.txt'
        header.write_bytes(header.read_bytes() + b'changed\n')
        monkeypatch.setattr(module, 'ASSETS', assets)
        target = tmp_path / name / 'notices'
        with pytest.raises(module.LicenseError, match='supplemental notice checksum mismatch: lxml'):
            module.collect(bundle, target, required_distributions=['lxml'])
        assert not target.exists()


def test_selects_actual_freezer_toc_files_not_every_installed_dependency(tmp_path):
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    toc = tmp_path / 'Analysis-00.toc'
    dist = metadata.distribution('pypdf')
    source = str(dist.locate_file('pypdf/__init__.py'))
    # The TOC shape is PyInstaller's literal tuple/list, with real installed files.
    toc.write_text(repr((['entry.py'], [('pypdf', source, 'PYMODULE')],
                         [('README.md', str(ROOT / 'README.md'), 'DATA')], [])))
    report = module.collect(bundle, tmp_path / 'notices', analysis_toc=toc)
    assert {d['name'] for d in report['distributions']} == {'pypdf', 'pyinstaller'}
    assert next(d for d in report['distributions'] if d['name'] == 'pypdf')['selection'] == 'analysis-toc'
    assert 'artifact-selection-review' in {b['id'] for b in report['blockers']}
    assert str(Path.home()) not in json.dumps(report)


def test_cli_generates_report_but_exits_nonzero_for_unresolved_release_prerequisites(tmp_path):
    import subprocess
    import sys
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    destination = tmp_path / 'notices'
    result = subprocess.run([sys.executable, str(ROOT / 'tools/collect_licenses.py'),
                             '--bundle', str(bundle), '--destination', str(destination),
                             '--distribution', 'pypdf'], capture_output=True, text=True)
    assert result.returncode == 2
    report = json.loads((destination / 'manifest.json').read_text())
    assert report['release_ready'] is False
    assert 'BLOCKED' in result.stdout
    notices = (destination / 'THIRD_PARTY_NOTICES.md').read_text()
    assert 'artifact-selection-review' in notices
    assert 'native-runtime-review' in notices


def test_vendored_notices_preserve_distinct_paths_and_original_bytes(tmp_path):
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    target = tmp_path / 'notices'
    report = module.collect(bundle, target, required_distributions=['setuptools', 'pillow'])
    setuptools = next(d for d in report['distributions'] if d['name'] == 'setuptools')
    filenames = [n['file'] for n in setuptools['notices']]
    assert len(filenames) == len(set(filenames)), 'vendored LICENSE filenames must not collide'
    for dist in report['distributions']:
        for notice in dist['notices']:
            assert hashlib.sha256((target / notice['file']).read_bytes()).hexdigest() == notice['sha256']
    assert any('jaraco' in name for name in filenames)
    assert any(name.endswith('/config/NOTICE') for name in filenames)
    assert 'based in part on the work of the Independent JPEG Group' in (target / 'THIRD_PARTY_NOTICES.md').read_text()
    assert 'based in part on the work of the FreeType Team' in (target / 'THIRD_PARTY_NOTICES.md').read_text()


def test_pyobjc_supplement_copies_public_text_not_test_binary_named_copying(tmp_path):
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    target = tmp_path / 'notices'
    report = module.collect(bundle, target, required_distributions=[
        'pyobjc-core', 'pyobjc-framework-Security', 'pyobjc-framework-UniformTypeIdentifiers'])
    for dist in report['distributions']:
        for notice in dist['notices']:
            text = (target / notice['file']).read_text()
            assert text.strip()
            assert not notice['file'].endswith(('.so', '.py', '.pyc'))
    core = next(d for d in report['distributions'] if d['name'] == 'pyobjc-core')
    assert any(n.get('source_url', '').endswith('/pyobjc_core-13.0.tar.gz') for n in core['notices'])


def test_refuses_stale_or_symlink_destinations_without_overwriting(tmp_path):
    import pytest
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    stale = tmp_path / 'stale'
    stale.mkdir()
    (stale / 'manifest.json').write_text('previous artifact')
    linked = tmp_path / 'linked'
    linked.symlink_to(stale, target_is_directory=True)
    for destination in (stale, linked, bundle):
        with pytest.raises(module.LicenseError, match='destination'):
            module.collect(bundle, destination, required_distributions=['pypdf'])
    assert (stale / 'manifest.json').read_text() == 'previous artifact'
    assert not list(bundle.iterdir())


def test_refuses_external_bundle_symlinks_without_reading_target(tmp_path):
    import pytest
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    (bundle / 'outside').symlink_to(tmp_path / 'not-shipped')
    with pytest.raises(module.LicenseError, match='symlink'):
        module.collect(bundle, tmp_path / 'notices', required_distributions=['pypdf'])
    assert not (tmp_path / 'notices').exists()


def test_certifi_mpl_notice_names_exact_corresponding_source(tmp_path):
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    target = tmp_path / 'notices'
    report = module.collect(bundle, target, required_distributions=['certifi'])
    dist = next(d for d in report['distributions'] if d['name'] == 'certifi')
    assert dist['source']['url'].startswith('https://files.pythonhosted.org/packages/')
    assert dist['source']['url'].endswith('/certifi-2026.10.23.tar.gz')
    assert len(dist['source']['sha256']) == 64
    assert dist['source']['url'] in (target / 'THIRD_PARTY_NOTICES.md').read_text()
    assert 'MPL-2.0' in (target / 'THIRD_PARTY_NOTICES.md').read_text()


def test_explicit_metadata_environment_refuses_empty_license_text(tmp_path):
    import pytest
    import shutil
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    site = tmp_path / 'site-packages'
    site.mkdir()
    for name in ('pypdf', 'pyinstaller'):
        dist = metadata.distribution(name)
        entry = next(p for p in dist.files if str(p).endswith('.dist-info/METADATA'))
        source = Path(str(dist.locate_file(entry))).parent
        shutil.copytree(source, site / source.name)
    empty = next(site.glob('pypdf-*.dist-info/licenses/LICENSE'))
    empty.write_bytes(b'')
    with pytest.raises(module.LicenseError, match='empty.*pypdf'):
        module.collect(bundle, tmp_path / 'notices', required_distributions=['pypdf'],
                       site_packages=[str(site)])
    assert not (tmp_path / 'notices').exists()


def test_proxy_tools_missing_wheel_license_uses_code_matched_upstream_but_reports_conflict(tmp_path):
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    target = tmp_path / 'notices'
    report = module.collect(bundle, target, required_distributions=['proxy_tools'])
    dist = next(d for d in report['distributions'] if d['name'] == 'proxy-tools')
    notice = dist['notices'][0]
    assert 'db43f1e35d4f90a65c5a4d56d9e9af88212ec6e6' in notice['source_url']
    assert 'The BSD License' in (target / notice['file']).read_text()
    assert 'proxy-tools-license-conflict' in {b['id'] for b in report['blockers']}
    assert report['release_ready'] is False


def test_authors_file_is_not_accepted_as_required_license(tmp_path):
    import pytest
    import shutil
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    site = tmp_path / 'site-packages'
    site.mkdir()
    for name in ('pypdf', 'pyinstaller'):
        dist = metadata.distribution(name)
        entry = next(p for p in (dist.files or []) if str(p).endswith('.dist-info/METADATA'))
        source = Path(str(dist.locate_file(entry))).parent
        shutil.copytree(source, site / source.name)
    license_file = next(site.glob('pypdf-*.dist-info/licenses/LICENSE'))
    license_file.rename(license_file.with_name('AUTHORS'))
    record = next(site.glob('pypdf-*.dist-info/RECORD'))
    record.write_text(record.read_text().replace('/licenses/LICENSE,', '/licenses/AUTHORS,'))
    with pytest.raises(module.LicenseError, match='required license text missing: pypdf'):
        module.collect(bundle, tmp_path / 'notices', required_distributions=['pypdf'],
                       site_packages=[str(site)])
    assert not (tmp_path / 'notices').exists()


def test_empty_cpython_runtime_license_fails_before_output(tmp_path):
    import pytest
    module = collector()
    bundle = tmp_path / 'Example.app'
    bundle.mkdir()
    empty = tmp_path / 'LICENSE.txt'
    empty.write_bytes(b'')
    with pytest.raises(module.LicenseError, match='CPython runtime license'):
        module.collect(bundle, tmp_path / 'notices', required_distributions=['pypdf'],
                       python_license=empty)
    assert not (tmp_path / 'notices').exists()
