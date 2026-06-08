"""Placement and shim contract for the structured_logging infrastructure module."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_top_level_module_exposes_public_api() -> None:
    module = importlib.import_module("fleetent.structured_logging")

    assert hasattr(module, "get_logger")
    assert hasattr(module, "configure_structured_logging")
    assert hasattr(module, "Logger")


def test_module_lives_at_top_level_path() -> None:
    module = importlib.import_module("fleetent.structured_logging")

    assert module.__file__ is not None
    located = Path(module.__file__)
    assert located.name == "structured_logging.py"
    assert located.parent.name == "fleetent"


def test_legacy_observability_path_still_works_via_shim() -> None:
    shim = importlib.import_module("fleetent.observability.structured_logging")
    target = importlib.import_module("fleetent.structured_logging")

    # Shim re-exports the same objects from the relocated module.
    assert shim.get_logger is target.get_logger
    assert shim.configure_structured_logging is target.configure_structured_logging
    assert shim.Logger is target.Logger
    assert shim._redact_value is target._redact_value
