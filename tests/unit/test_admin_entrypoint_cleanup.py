"""Regression tests for the retired admin CLI shim."""

from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path

import pytest


def test_fleetent_admin_console_script_points_to_shim() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())

    assert (
        pyproject["project"]["scripts"]["fleetent-admin"] == "fleetent._shims:fleetent_admin_shim"
    )


def test_legacy_admin_module_is_not_importable() -> None:
    sys.modules.pop("fleetent.admin", None)

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fleetent.admin")
