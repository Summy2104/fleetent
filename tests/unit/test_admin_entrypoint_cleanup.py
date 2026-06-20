"""Regression tests for the retired admin CLI shim."""

from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path

import pytest


def test_legacy_console_scripts_removed_from_pyproject() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    scripts = pyproject["project"]["scripts"]

    assert "fleetent-admin" not in scripts
    assert "fleetent-node" not in scripts


def test_legacy_admin_module_is_not_importable() -> None:
    sys.modules.pop("fleetent.admin", None)

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fleetent.admin")
