"""A separately labelled dependency candidate is not publication clearance."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import runpy
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'tools/build_pywebview_candidate.py'


def module():
    assert TOOL.is_file(), 'reproducible pywebview candidate builder is not implemented'
    return runpy.run_path(str(TOOL))


def source_wheel(tmp_path):
    path = tmp_path / 'pywebview-6.2.1-py3-none-any.whl'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('webview/__init__.py', 'from proxy_tools import module_property\n')
        archive.writestr('webview/unchanged.py', 'SYNTHETIC_TEST_MARKER = 1\n')
        archive.writestr('pywebview-6.2.1.dist-info/METADATA',
                         'Metadata-Version: 2.4\nName: pywebview\nVersion: 6.2.1\n'
                         'Requires-Dist: proxy_tools\nRequires-Dist: bottle\n\nSynthetic fixture\n')
        archive.writestr('pywebview-6.2.1.dist-info/WHEEL', 'Wheel-Version: 1.0\nTag: py3-none-any\n')
        archive.writestr('pywebview-6.2.1.dist-info/licenses/LICENSE', 'Synthetic original license bytes\n')
        archive.writestr('pywebview-6.2.1.dist-info/RECORD', '')
    return path


def test_candidate_has_distinct_version_no_proxy_requirement_and_valid_record(tmp_path, monkeypatch):
    loaded = module()
    wheel = source_wheel(tmp_path)
    build = loaded['build_candidate']
    # Synthetic archive tests wheel transformation; real locked wheel is exercised separately.
    monkeypatch.setitem(build.__globals__, 'WHEEL_SHA256', hashlib.sha256(wheel.read_bytes()).hexdigest())
    monkeypatch.setitem(build.__globals__, 'INIT_SHA256', hashlib.sha256(b'from proxy_tools import module_property\n').hexdigest())
    first = build(wheel, tmp_path / 'first')
    second = build(wheel, tmp_path / 'second')
    assert first['version'] == '6.2.1+kh.1'
    assert first['release_ready'] is False
    output = tmp_path / 'first' / first['wheel_file']
    assert output.read_bytes() == (tmp_path / 'second' / second['wheel_file']).read_bytes()
    with zipfile.ZipFile(output) as archive:
        prefix = 'pywebview-6.2.1+kh.1.dist-info/'
        text = archive.read(prefix + 'METADATA').decode()
        assert 'Version: 6.2.1+kh.1\n' in text
        assert 'Requires-Dist: bottle\n' in text
        assert 'proxy_tools' not in text
        assert archive.read('webview/unchanged.py') == b'SYNTHETIC_TEST_MARKER = 1\n'
        assert archive.read(prefix + 'licenses/LICENSE') == b'Synthetic original license bytes\n'
        assert archive.read(prefix + 'licenses/KNOWLEDGE-HUB-BACKPORT-LICENSE').startswith(b'BSD 3-Clause License')
        provenance = json.loads(archive.read(prefix + 'knowledge_hub_backport.json'))
        assert provenance['upstream_commit'] == '238c6705ada00ee3d903c78247e71d9bfecbab87'
        assert str(tmp_path) not in json.dumps(provenance)
        record_name = prefix + 'RECORD'
        records = list(csv.reader(io.StringIO(archive.read(record_name).decode())))
        assert {row[0] for row in records} == set(archive.namelist())
        for name, digest, size in records:
            if name == record_name:
                assert digest == size == ''
            else:
                content = archive.read(name)
                assert digest == 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip('=')
                assert int(size) == len(content)
    assert (tmp_path / 'first/evidence.json').is_file()


@pytest.mark.parametrize('tamper', ['wheel', 'initializer', 'backport', 'license', 'metadata', 'member-path'])
def test_candidate_input_denials_leave_no_output(tmp_path, monkeypatch, tamper):
    loaded = module()
    build = loaded['build_candidate']
    wheel = source_wheel(tmp_path)
    assets = tmp_path / 'assets'
    assets.mkdir()
    for name in ('__init__.py', 'LICENSE', 'PROVENANCE.json'):
        (assets / name).write_bytes((ROOT / 'assets/vendor/pywebview' / name).read_bytes())
    monkeypatch.setitem(build.__globals__, 'ASSETS', assets)
    original_init = b'from proxy_tools import module_property\n'
    monkeypatch.setitem(build.__globals__, 'INIT_SHA256', hashlib.sha256(original_init).hexdigest())
    if tamper in ('metadata', 'member-path'):
        with zipfile.ZipFile(wheel) as archive:
            entries = {n: archive.read(n) for n in archive.namelist()}
        if tamper == 'metadata':
            name = 'pywebview-6.2.1.dist-info/METADATA'
            entries[name] = entries[name].replace(b'Version: 6.2.1\n', b'Version: 6.2.0\n')
        else:
            entries['webview/../../escape'] = b'not permitted'
        with zipfile.ZipFile(wheel, 'w') as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
    monkeypatch.setitem(build.__globals__, 'WHEEL_SHA256', hashlib.sha256(wheel.read_bytes()).hexdigest())
    if tamper == 'wheel':
        wheel.write_bytes(wheel.read_bytes() + b'tampered')
    elif tamper == 'initializer':
        monkeypatch.setitem(build.__globals__, 'INIT_SHA256', '0' * 64)
    elif tamper in ('backport', 'license'):
        path = assets / ('__init__.py' if tamper == 'backport' else 'LICENSE')
        path.write_bytes(path.read_bytes() + b'tampered')
    output = tmp_path / 'out'
    with pytest.raises(ValueError):
        build(wheel, output)
    assert not output.exists()
    assert not (tmp_path / 'escape').exists()


@pytest.mark.parametrize('kind', ['existing', 'symlink'])
def test_candidate_never_overwrites_an_output_location(tmp_path, monkeypatch, kind):
    build = module()['build_candidate']
    wheel = source_wheel(tmp_path)
    monkeypatch.setitem(build.__globals__, 'WHEEL_SHA256', hashlib.sha256(wheel.read_bytes()).hexdigest())
    monkeypatch.setitem(build.__globals__, 'INIT_SHA256', hashlib.sha256(b'from proxy_tools import module_property\n').hexdigest())
    preserved = tmp_path / 'preserved'
    preserved.mkdir()
    marker = preserved / 'marker'
    marker.write_bytes(b'unchanged synthetic output')
    output = preserved
    if kind == 'symlink':
        linked = tmp_path / 'linked'
        linked.symlink_to(preserved, target_is_directory=True)
        output = linked / 'new-candidate'
    with pytest.raises(ValueError, match='fresh directory'):
        build(wheel, output)
    assert marker.read_bytes() == b'unchanged synthetic output'
    assert sorted(p.name for p in preserved.iterdir()) == ['marker']
