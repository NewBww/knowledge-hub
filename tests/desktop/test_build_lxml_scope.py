"""Freeze only XML capabilities actually used by the application."""
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]


def test_unused_isoschematron_module_is_excluded_without_excluding_lxml(tmp_path):
    module = runpy.run_path(str(ROOT / 'tools/build_macos.py'))
    command = module['pyinstaller_command'](tmp_path, tmp_path, tmp_path,
                                             {'bundle_id': 'com.synthetic', 'architecture': 'arm64'})
    exclusions = [command[index + 1] for index, item in enumerate(command) if item == '--exclude-module']
    assert 'lxml.isoschematron' in exclusions, 'unused schema extractors without established redistribution grant must not ship'
    assert 'lxml' not in exclusions
    assert 'lxml.etree' not in exclusions
