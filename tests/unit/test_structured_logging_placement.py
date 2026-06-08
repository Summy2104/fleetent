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


def test_legacy_observability_path_is_removed() -> None:
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fleetent.observability.structured_logging")


def test_no_residual_legacy_path_imports() -> None:
    legacy_module = "fleetent.observability" + ".structured_logging"
    legacy_from = "fleetent.observability import " + "structured_logging"
    self_path = Path(__file__).resolve()
    roots = (Path("src/fleetent"), Path("tests"))
    offenders: list[str] = []
    for root in roots:
        for py in root.rglob("*.py"):
            if py.resolve() == self_path:
                continue
            text = py.read_text(encoding="utf-8")
            if legacy_module in text or legacy_from in text:
                offenders.append(str(py))
    assert not offenders, f"residual legacy structured_logging path imports: {offenders}"
