"""Release metadata is consistent across the installer and running adapters."""
from pathlib import Path
import tomllib
from knowledge_hub.http import VERSION


def test_revised_preview_has_distinct_consistent_version():
    project = tomllib.loads((Path(__file__).resolve().parents[2] / 'pyproject.toml').read_text())['project']
    assert project['version'] == VERSION == '0.3.0'
