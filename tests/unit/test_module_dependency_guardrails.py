"""Dependency guardrails for intelligence-layer dissolution."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

_SRC_ROOT = Path("src/fleetent")


_COMPONENTS = {
    "governance",
    "im_gateway",
    "integrations",
    "knowledge_base",
    "long_term_ctx",
    "memory",
    "observability",
    "reflection",
    "runtime",
    "session",
    "tools",
    "vector_store",
}

_ALLOWED_VECTOR_STORE_EXTERNAL_IMPORTS = {
    "fleetent.agent_config",
    "fleetent.config",
    "fleetent.model",
}


def _iter_imported_modules(node: ast.AST) -> list[str]:
    modules: list[str] = []
    for statement in ast.walk(node):
        if isinstance(statement, ast.Import):
            modules.extend(alias.name for alias in statement.names)
        elif isinstance(statement, ast.ImportFrom) and statement.module:
            modules.append(statement.module)
    return modules


def _module_name(path: Path) -> str:
    rel = path.relative_to(_SRC_ROOT).with_suffix("")
    parts = rel.parts
    filtered = [part for part in parts if part != "__init__"]
    return "fleetent." + ".".join(filtered)


def _owns_component(module: str, component: str) -> bool:
    if module.startswith("fleetent."):
        legacy_module = "fleetent." + component
        return module.startswith(legacy_module)
    return module.startswith(f"fleetent.{component}")


def _is_imported_from(prefixes: Iterable[str], imported_modules: set[str]) -> bool:
    return any(
        imported_module.startswith(prefix)
        for imported_module in imported_modules
        for prefix in prefixes
        if imported_module
    )


def _src_python_paths() -> Iterable[Path]:
    return (
        path
        for path in _SRC_ROOT.rglob("*.py")
        if path.is_file() and "intelligence" not in path.parts and path.name != "__init__.py"
    )


def _top_level_component(module_name: str) -> str | None:
    parts = module_name.split(".")
    if len(parts) < 2:
        return None
    return parts[1]


def test_forbidden_edges_for_dissolution() -> None:
    for path in _src_python_paths():
        module_name = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_modules = set(_iter_imported_modules(tree))

        if module_name.startswith("fleetent.knowledge_base.retrieval"):
            assert not _is_imported_from(
                ["fleetent.knowledge_base.ingest"],
                imported_modules,
            ), (
                f"{module_name} imports from knowledge_base.ingest, "
                "violating retrieval -> ingest boundary"
            )

        if _owns_component(module_name, "memory") or _owns_component(module_name, "knowledge_base"):
            assert not _is_imported_from(
                [
                    "fleetent.long_term_ctx",
                    "fleetent.reflection",
                    "fleetent.long_term_ctx",
                    "fleetent.reflection",
                ],
                imported_modules,
            ), (
                f"{module_name} imports aggregation modules, "
                "forbidden by memory/KB -> long_term_ctx/reflection boundary"
            )

        component = _top_level_component(module_name)
        if component in _COMPONENTS:
            assert not any(
                imported.startswith("fleetent.platform") for imported in imported_modules
            ), f"{module_name} imports fleetent.platform despite component boundary"

        if module_name.startswith("fleetent.vector_store"):
            for imported in imported_modules:
                if not imported.startswith("fleetent."):
                    continue
                if imported.startswith("fleetent.vector_store"):
                    continue
                if any(
                    imported.startswith(prefix) for prefix in _ALLOWED_VECTOR_STORE_EXTERNAL_IMPORTS
                ):
                    continue
                raise AssertionError(
                    f"{module_name} imports business module {imported}, "
                    "violating vector_store -> infrastructure-only"
                )
