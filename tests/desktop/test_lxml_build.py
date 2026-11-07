"""An alternative lxml build must not silently use old SDK XML headers."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def builder():
    spec = importlib.util.spec_from_file_location('lxml_builder', ROOT / 'tools/build_lxml_macos.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rejects_runtime_or_header_version_downgrade():
    module = builder()
    valid = {'xml_runtime': [2, 15, 2], 'xml_compiled': [2, 15, 2],
             'xslt_runtime': [1, 1, 45], 'xslt_compiled': [1, 1, 45]}
    module.validate_versions(valid)
    for key in valid:
        broken = {**valid, key: [2, 9, 13] if key.startswith('xml_') else [1, 1, 35]}
        with pytest.raises(ValueError, match='version'):
            module.validate_versions(broken)


def test_native_validation_rejects_the_original_static_iconv_wheel():
    from lxml import etree
    module = builder()
    with pytest.raises(ValueError, match='iconv'):
        module.inspect_native(Path(etree.__file__))


def test_build_environment_is_consistent_and_cannot_inherit_staticbuild(tmp_path):
    module = builder()
    env = module.build_environment(tmp_path, {'STATICBUILD': 'true', 'CFLAGS': '-I/untrusted',
                                               'LDFLAGS': '-L/untrusted'})
    assert 'STATICBUILD' not in env
    assert env['MACOSX_DEPLOYMENT_TARGET'] == '12.0'
    assert env['INCLUDE'].split() == [str(tmp_path / 'include'), str(tmp_path / 'include/libxml2')]
    assert '-mmacosx-version-min=12.0' in env['CFLAGS']
    assert '/untrusted' not in repr(env)


def test_build_refuses_existing_workspace_before_any_write(tmp_path):
    module = builder()
    marker = tmp_path / 'keep'
    marker.write_text('existing')
    with pytest.raises(ValueError, match='fresh'):
        module.main(['--work', str(tmp_path)])
    assert marker.read_text() == 'existing'
    assert list(tmp_path.iterdir()) == [marker]


def test_unimplemented_build_fails_closed_without_creating_workspace(tmp_path, monkeypatch):
    module = builder()
    work = tmp_path / 'fresh-build'
    def forbidden(*args, **kwargs):
        pytest.fail('validation must not run a build or download')
    monkeypatch.setattr(module.subprocess, 'run', forbidden)
    monkeypatch.setattr(module.urllib.request, 'urlopen', forbidden)
    with pytest.raises(RuntimeError, match='not implemented'):
        module.main(['--work', str(work)])
    assert not work.exists()
