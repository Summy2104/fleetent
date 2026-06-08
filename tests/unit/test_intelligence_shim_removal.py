"""Guardrails for intelligence-layer collapse."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

_SRC_ROOT = Path("src/fleetent")


def _iter_source_files() -> Iterable[Path]:
    for path in _SRC_ROOT.rglob("*.py"):
        if "intelligence" in path.parts:
            continue
        if path.name == "__init__.py":
            continue
        yield path


def _iter_imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_no_fleetent_intelligence_imports_in_source_code() -> None:
    offenders: list[str] = []
    for path in _iter_source_files():
        imported_modules = _iter_imported_modules(
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path)),
        )
        if any(
            module == "fleetent.intelligence" or module.startswith("fleetent.intelligence.")
            for module in imported_modules
        ):
            offenders.append(str(path))

    assert not offenders, "legacy intelligence import path still in use:\n" + "".join(
        f"- {path}\n" for path in offenders
    )


def test_intelligence_directory_shim_removed() -> None:
    assert not (Path("src/fleetent/intelligence").exists()), (
        "intelligence package should be removed in stage 5"
    )
