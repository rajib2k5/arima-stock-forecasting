"""Project-level rules: the version is stated once and agrees everywhere, and every direct
dependency is pinned to an exact version that uv.lock actually resolved."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

import arima_forecasting

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
LOCK = tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))

PIN = re.compile(r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[0-9][A-Za-z0-9.+!_-]*)")


def direct_dependencies() -> list[str]:
    runtime = PYPROJECT["project"]["dependencies"]
    dev = PYPROJECT["dependency-groups"]["dev"]
    return [*runtime, *dev]


def normalise(name: str) -> str:
    # PEP 503: package names compare case-insensitively with "-", "_" and "." as one character.
    return re.sub(r"[-_.]+", "-", name).lower()


def test_version_in_code_matches_pyproject():
    assert arima_forecasting.__version__ == PYPROJECT["project"]["version"] == "0.1.0"


def test_python_is_pinned_to_3_12():
    assert PYPROJECT["project"]["requires-python"] == "==3.12.*"
    assert (REPO / ".python-version").read_text().strip() == "3.12"


def test_there_are_direct_dependencies_to_check():
    # Guard against the checks below passing vacuously on an empty list.
    names = {normalise(PIN.fullmatch(d).group("name")) for d in direct_dependencies()}
    assert {"numpy", "scipy", "statsmodels", "pmdarima", "scikit-learn", "pandas", "yfinance",
            "matplotlib", "pytest", "nbformat", "nbclient", "ipykernel"} <= names


@pytest.mark.parametrize("spec", direct_dependencies())
def test_every_direct_dependency_is_pinned_with_double_equals(spec):
    assert PIN.fullmatch(spec), f"{spec!r} must look like name==1.2.3"


@pytest.mark.parametrize("spec", direct_dependencies())
def test_pin_equals_the_version_in_uv_lock(spec):
    match = PIN.fullmatch(spec)
    locked = {normalise(p["name"]): p["version"] for p in LOCK["package"]}
    assert locked[normalise(match.group("name"))] == match.group("version")
