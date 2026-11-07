"""Version-matched regression contract for the seven reviewed Dependabot alerts."""
from importlib.metadata import version
from pathlib import Path
import tomllib

from packaging.requirements import Requirement
from packaging.version import Version
import pytest


ROOT = Path(__file__).resolve().parents[2]
# Starlette's five advisories are all patched by 1.3.1; AnyIO's two by 4.14.2.
PATCHED_FLOORS = {"starlette": "1.3.1", "anyio": "4.14.2"}


@pytest.mark.parametrize("name,floor", PATCHED_FLOORS.items())
def test_reviewed_security_floors_cover_manifest_lock_and_runtime(name, floor):
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    requirement = next(
        Requirement(raw) for raw in manifest["project"]["dependencies"]
        if Requirement(raw).name == name
    )
    locked = [package for package in lock["package"] if package["name"] == name]
    assert len(locked) == 1
    resolved = Version(locked[0]["version"])
    patched = Version(floor)
    assert resolved >= patched, f"{name} lock remains below reviewed patched floor {floor}"
    assert resolved in requirement.specifier
    assert patched in requirement.specifier
    # A lower bound is required: a safe lock alone must not permit vulnerable re-resolution.
    assert any(
        spec.operator in {">=", "==", "~="} and Version(spec.version) >= patched
        for spec in requirement.specifier
    ), f"{name} manifest permits versions below reviewed patched floor {floor}"
    assert Version(version(name)) == resolved, "regressions must run with the locked dependency"
