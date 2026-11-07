"""Opt-in candidate selection uses file fixtures, never pip or the project venv."""
import hashlib
import importlib.util
import json
import platform
from pathlib import Path
import struct
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]


def builder():
    spec = importlib.util.spec_from_file_location('lxml_packaging', ROOT / 'tools/build_macos.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def synthetic_arm64_host(monkeypatch):
    """Validate arm64 file fixtures, without loading or building native code."""
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(platform, 'machine', lambda: 'arm64')


@pytest.fixture
def candidate(tmp_path, synthetic_arm64_host):
    module = builder()
    tag = f'cp{sys.version_info.major}{sys.version_info.minor}'
    suffix = f'cpython-{sys.version_info.major}{sys.version_info.minor}-darwin.so'
    native = {f'lxml/{name}.{suffix}': struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 6, 0, 0, 0, 0) + name.encode()
              for name in ('etree', 'objectify')}
    files = {'lxml/__init__.py': b'__version__ = "6.1.3"\n', **native,
             'lxml-6.1.3.dist-info/METADATA': b'Name: lxml\nVersion: 6.1.3\n',
             'lxml-6.1.3.dist-info/WHEEL': f'Wheel-Version: 1.0\nTag: {tag}-{tag}-macosx_12_0_arm64\n'.encode()}
    wheel = tmp_path / f'lxml-6.1.3-{tag}-{tag}-macosx_12_0_arm64.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    evidence = {'status': 'candidate-verified-not-release-cleared', 'release_ready': False,
                'publication_blocked': True, 'python': sys.version,
                'wheel': {'file': str(wheel), 'sha256': digest(wheel.read_bytes())},
                'sources': {name: {'url': url, 'sha256': sha} for name, (url, sha) in module_sources().items()},
                'commands': [{'returncode': 0, 'argv': ['configure', '--with-schematron']}] * 7,
                'probe': {'xml_runtime': [2, 15, 2], 'xml_compiled': [2, 15, 2],
                          'xslt_runtime': [1, 1, 45], 'xslt_compiled': [1, 1, 45],
                          'docx': {'status': 'extracted', 'text': 'Synthetic paragraph\nTable preserved'}},
                'native': [{'file': Path(name).name, 'sha256': digest(data),
                            'linked_libraries': ['/usr/lib/libSystem.B.dylib', '/usr/lib/libiconv.2.dylib', '/usr/lib/libz.1.dylib'],
                            'static_iconv_symbols': False} for name, data in native.items()]}
    path = tmp_path / 'evidence.json'
    path.write_text(json.dumps(evidence))
    return wheel, evidence['wheel']['sha256'], path, evidence


def module_sources():
    spec = importlib.util.spec_from_file_location('lxml_native', ROOT / 'tools/build_lxml_macos.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SOURCES


@pytest.mark.parametrize('host,architecture', [('linux', 'arm64'), ('darwin', 'x86_64')])
def test_candidate_rejects_unsupported_host_before_staging(candidate, tmp_path, monkeypatch, host, architecture):
    wheel, sha, evidence, _ = candidate
    module = builder()
    monkeypatch.setattr(module.sys, 'platform', host)
    monkeypatch.setattr(module.platform, 'machine', lambda: architecture)
    destination = tmp_path / 'isolated'
    with pytest.raises(ValueError, match='runtime/architecture mismatch'):
        module.stage_lxml_candidate(wheel, sha, evidence, destination)
    assert not destination.exists()


@pytest.mark.parametrize('fault', ['checksum', 'evidence-wheel', 'status', 'runtime', 'architecture',
    'native-hash', 'missing-native', 'static-iconv', 'source', 'failed-command', 'versions',
    'missing-docx', 'clearance', 'traversal', 'zip-symlink', 'duplicate', 'wheel-symlink',
    'evidence-symlink', 'destination-symlink', 'ancestor-symlink', 'native-architecture', 'stale-features'])
def test_rejects_unsafe_or_stale_candidate_before_staging(candidate, tmp_path, fault):
    wheel, sha, evidence, report = candidate
    destination = tmp_path / 'isolated'
    if fault == 'checksum':
        sha = '0' * 64
    elif fault == 'evidence-wheel':
        report['wheel']['sha256'] = '0' * 64
    elif fault == 'status':
        report['status'] = 'building'
    elif fault == 'runtime':
        report['python'] = '3.14.0 stale runtime'
    elif fault == 'native-hash':
        report['native'][0]['sha256'] = '0' * 64
    elif fault == 'missing-native':
        report['native'].pop()
    elif fault == 'static-iconv':
        report['native'][0]['static_iconv_symbols'] = True
    elif fault == 'source':
        report['sources']['lxml']['sha256'] = '0' * 64
    elif fault == 'failed-command':
        report['commands'][0]['returncode'] = 1
    elif fault == 'stale-features':
        report['commands'] = [{'returncode': 0, 'argv': ['configure']}] * 7
    elif fault == 'versions':
        report['probe']['xml_runtime'] = [2, 9, 0]
    elif fault == 'missing-docx':
        report['probe'].pop('docx')
    elif fault == 'clearance':
        report['release_ready'] = True
    elif fault == 'architecture':
        renamed = wheel.with_name(wheel.name.replace('arm64', 'x86_64'))
        wheel.rename(renamed)
        wheel = renamed
    elif fault in ('traversal', 'zip-symlink', 'duplicate', 'native-architecture'):
        with zipfile.ZipFile(wheel) as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
        if fault == 'native-architecture':
            name = 'lxml/' + report['native'][0]['file']
            contents[name] = struct.pack('<II', 0xfeedfacf, 0x1000007) + contents[name][8:]
            report['native'][0]['sha256'] = digest(contents[name])
        with zipfile.ZipFile(wheel, 'w') as archive:
            for name, data in contents.items():
                archive.writestr(name, data)
            if fault == 'traversal':
                archive.writestr('../escaped', b'bad')
            elif fault == 'zip-symlink':
                info = zipfile.ZipInfo('lxml/link')
                info.create_system = 3
                info.external_attr = 0o120777 << 16
                archive.writestr(info, '/outside')
            elif fault == 'duplicate':
                with pytest.warns(UserWarning, match='Duplicate name'):
                    archive.writestr('lxml/__init__.py', b'changed')
        sha = digest(wheel.read_bytes())
        report['wheel']['sha256'] = sha
    elif fault in ('wheel-symlink', 'evidence-symlink'):
        target = wheel if fault == 'wheel-symlink' else evidence
        moved = target.with_name(target.name + '.real')
        target.rename(moved)
        target.symlink_to(moved)
    elif fault == 'destination-symlink':
        real = tmp_path / 'real'
        real.mkdir()
        destination.symlink_to(real, target_is_directory=True)
    elif fault == 'ancestor-symlink':
        real = tmp_path / 'real'
        real.mkdir()
        link = tmp_path / 'link'
        link.symlink_to(real, target_is_directory=True)
        destination = link / 'isolated'
    if fault != 'evidence-symlink':
        evidence.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        builder().stage_lxml_candidate(wheel, sha, evidence, destination)
    assert not (tmp_path / 'escaped').exists()
    assert not (destination / 'lxml').exists()


def test_standard_auxiliary_native_is_hash_inventoried(candidate, tmp_path):
    wheel, _, evidence, report = candidate
    name = 'lxml/builder.cpython-312-darwin.so'
    data = struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 6, 0, 0, 0, 0) + b'builder'
    with zipfile.ZipFile(wheel, 'a') as archive:
        archive.writestr(name, data)
    sha = digest(wheel.read_bytes())
    report['wheel']['sha256'] = sha
    evidence.write_text(json.dumps(report))
    staged = builder().stage_lxml_candidate(wheel, sha, evidence, tmp_path / 'staged')
    assert staged['files'][name] == digest(data)


def test_prepare_candidate_is_explicit_and_pins_freezer_search(candidate, tmp_path):
    wheel, sha, evidence, _ = candidate
    module = builder()
    plan = module.prepare_build(ROOT, tmp_path / 'out', tmp_path / 'work',
                               lxml_wheel=wheel, lxml_sha256=sha, lxml_evidence=evidence)
    command = plan['pyinstaller']
    assert command[1:3] == ['-E', '-s']
    assert 'freeze_candidate.py' in command[3]
    assert command[command.index('--paths') + 1] == str(tmp_path / 'work/lxml-candidate')
    assert plan['lxml_candidate']['wheel_sha256'] == sha
    assert (tmp_path / 'work/lxml-candidate-provenance.json').is_file()
    for missing in ('lxml_wheel', 'lxml_sha256', 'lxml_evidence'):
        kwargs = dict(lxml_wheel=wheel, lxml_sha256=sha, lxml_evidence=evidence)
        kwargs.pop(missing)
        with pytest.raises(ValueError, match='together'):
            module.prepare_build(ROOT, tmp_path / 'out2', tmp_path / 'work2', **kwargs)


def test_selection_verification_rejects_upstream_toc(candidate, tmp_path):
    wheel, sha, evidence, _ = candidate
    module = builder()
    stage = tmp_path / 'candidate'
    provenance = module.stage_lxml_candidate(wheel, sha, evidence, stage)
    toc = tmp_path / 'Analysis-00.toc'
    records = [(f'lxml.{Path(item["file"]).name.split(".")[0]}', str(stage / 'lxml' / item['file']), 'EXTENSION') for item in provenance['native']]
    toc.write_text(repr(([], records)))
    module.verify_lxml_selection(toc, stage, provenance)
    records[0] = (records[0][0], str(tmp_path / 'venv' / provenance['native'][0]['file']), 'EXTENSION')
    toc.write_text(repr(([], records)))
    with pytest.raises(ValueError, match='selection'):
        module.verify_lxml_selection(toc, stage, provenance)


def test_candidate_cannot_clear_publication_even_with_clean_collector(candidate, tmp_path, monkeypatch):
    # Supplemental orchestration check: the candidate never grants license clearance.
    import plistlib
    module = builder()
    wheel, sha, evidence, _ = candidate
    plan = module.prepare_build(ROOT, tmp_path / 'out', tmp_path / 'work',
                                lxml_wheel=wheel, lxml_sha256=sha, lxml_evidence=evidence)
    app = plan['app']
    (app / 'Contents/Resources').mkdir(parents=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({}))
    monkeypatch.setattr(module, 'prepare_build', lambda *args, **kwargs: plan)
    monkeypatch.setattr(module, 'validate_sparkle_distribution', lambda path: path)
    monkeypatch.setattr(module, 'verify_lxml_selection', lambda *args: None)
    monkeypatch.setattr(module, 'embed_sparkle', lambda *args: None)
    monkeypatch.setattr(module, 'collect_bundle_notices', lambda *args, **kwargs: {'release_ready': True, 'blockers': []})
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: None)
    signed = []
    monkeypatch.setattr(module, 'sign_app', lambda *args: signed.append(True))
    with pytest.raises(RuntimeError, match='Candidate publication blocked'):
        module.main(['--out', str(tmp_path / 'out'), '--sparkle-distribution', str(tmp_path / 'sdk')])
    assert not signed
    assert json.loads((app / 'Contents/Resources/lxml-candidate-provenance.json').read_text())['publication_blocked'] is True


def test_candidate_stages_exact_bytes_with_blocked_provenance(candidate, tmp_path):
    wheel, sha, evidence, _ = candidate
    destination = tmp_path / 'isolated'
    report = builder().stage_lxml_candidate(wheel, sha, evidence, destination)
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            assert (destination / name).read_bytes() == archive.read(name)
    assert report['wheel_sha256'] == sha
    assert report['evidence_sha256'] == digest(evidence.read_bytes())
    assert report['publication_blocked'] is True
    assert report['release_ready'] is False
    assert str(tmp_path) not in json.dumps(report)
