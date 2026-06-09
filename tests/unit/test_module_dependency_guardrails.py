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

# Top-level shared modules (e.g. ``fleetent.user_store``) sit outside the component
# allowlist the direct-edge guard checks, so an agent runtime module that imports one
# of them — which in turn imports ``fleetent.platform`` — leaks the platform dependency
# transitively without tripping the direct check. This set pins the *currently known*
# leaks so any NEW transitive leak fails the build; the ratchet test also fails if a
# pinned module stops leaking, forcing this set to shrink as the leaks get fixed.
_KNOWN_TRANSITIVE_PLATFORM_LEAKS: set[str] = {
    # user_store.authenticate()/get_or_create_im_user() hard-import
    # fleetent.platform.user_management / im_gateway_management unconditionally, so the
    # standalone `fleetent agent run` Bearer-auth path (agent_app:_authenticate) reaches
    # platform. Remove once those imports degrade gracefully when platform is absent.
    "fleetent.user_store",
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


_BUSINESS_CAPABILITY_PREFIXES = (
    "fleetent.runtime",
    "fleetent.memory",
    "fleetent.knowledge_base",
    "fleetent.reflection",
    "fleetent.long_term_ctx",
    "fleetent.session",
    "fleetent.tools",
)


def test_audit_log_toplevel_infra_boundary() -> None:
    import importlib

    module = importlib.import_module("fleetent.audit_log")
    assert module.__file__ is not None
    located = Path(module.__file__)
    assert located.name == "audit_log.py", (
        f"fleetent.audit_log must be at the top-level src/fleetent/audit_log.py, "
        f"got {located}"
    )
    assert located.parent.name == "fleetent", (
        f"fleetent.audit_log must be a top-level infrastructure module, "
        f"not nested under {located.parent.name}"
    )

    tree = ast.parse(located.read_text(encoding="utf-8"), filename=str(located))
    imported_modules = set(_iter_imported_modules(tree))

    assert not _is_imported_from(_BUSINESS_CAPABILITY_PREFIXES, imported_modules), (
        "fleetent.audit_log imports a business capability module, "
        "violating its infrastructure-only boundary"
    )
    assert not _is_imported_from(["fleetent.platform"], imported_modules), (
        "fleetent.audit_log imports fleetent.platform, "
        "violating its infrastructure-only boundary"
    )


def test_structured_logging_infra_boundary() -> None:
    import importlib

    module = importlib.import_module("fleetent.structured_logging")
    assert module.__file__ is not None
    located = Path(module.__file__)
    assert located.name == "structured_logging.py"
    assert located.parent.name == "fleetent"

    tree = ast.parse(located.read_text(encoding="utf-8"), filename=str(located))
    imported_modules = set(_iter_imported_modules(tree))

    assert not _is_imported_from(_BUSINESS_CAPABILITY_PREFIXES, imported_modules), (
        "fleetent.structured_logging imports a business capability module, "
        "violating its infrastructure-only boundary"
    )
    assert not _is_imported_from(["fleetent.platform"], imported_modules), (
        "fleetent.structured_logging imports fleetent.platform, "
        "violating its infrastructure-only boundary"
    )


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


def _fleetent_import_targets(node: ast.AST) -> set[str]:
    """Every ``fleetent.*`` dotted name referenced by import statements, including lazy
    (function-local) ones an ``ast.walk`` reaches.

    Unlike ``_iter_imported_modules``, this expands ``from fleetent import user_store``
    to ``fleetent.user_store`` so module-to-module edges survive graph traversal.
    """
    names: set[str] = set()
    for statement in ast.walk(node):
        if isinstance(statement, ast.Import):
            names.update(alias.name for alias in statement.names)
        elif isinstance(statement, ast.ImportFrom) and statement.module and statement.level == 0:
            names.add(statement.module)
            names.update(f"{statement.module}.{alias.name}" for alias in statement.names)
    return {name for name in names if name == "fleetent" or name.startswith("fleetent.")}


def _resolve_module(dotted: str, universe: set[str]) -> str | None:
    """Map an imported dotted name to the longest prefix that is a real module."""
    parts = dotted.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if candidate in universe:
            return candidate
    return None


def _agent_reachable_platform_leaks() -> dict[str, list[str]]:
    """Modules reachable from an agent runtime component that import ``fleetent.platform``.

    Returns a map of leaking module -> an import path back to a seed component, so a
    failure message can point at the chain that introduced the leak.
    """
    paths = [p for p in _SRC_ROOT.rglob("*.py") if p.is_file() and "intelligence" not in p.parts]
    universe = {_module_name(p) for p in paths}

    edges: dict[str, set[str]] = {}
    leaks: set[str] = set()
    for path in paths:
        module = _module_name(path)
        targets = _fleetent_import_targets(ast.parse(path.read_text(encoding="utf-8")))
        if any(target.startswith("fleetent.platform") for target in targets):
            leaks.add(module)
        resolved = {_resolve_module(t, universe) for t in targets}
        # Platform is a sink: we record the leak above but never traverse into it.
        edges[module] = {
            m for m in resolved if m and m != module and not m.startswith("fleetent.platform")
        }

    seeds = [m for m in universe if _top_level_component(m) in _COMPONENTS]
    parent: dict[str, str] = {}
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for target in edges.get(current, set()):
            if target not in seen:
                parent.setdefault(target, current)
                stack.append(target)

    found: dict[str, list[str]] = {}
    for module in sorted(seen & leaks):
        chain = [module]
        cursor = module
        while cursor in parent:
            cursor = parent[cursor]
            chain.append(cursor)
        found[module] = chain
    return found


def test_no_transitive_platform_leak_through_shared_modules() -> None:
    leaks = _agent_reachable_platform_leaks()

    new_leaks = {
        m: chain for m, chain in leaks.items() if m not in _KNOWN_TRANSITIVE_PLATFORM_LEAKS
    }
    assert not new_leaks, "agent runtime transitively reaches fleetent.platform via: " + "; ".join(
        f"{module} (imported through {' <- '.join(chain)})" for module, chain in new_leaks.items()
    )

    # Ratchet: a pinned leak that no longer leaks must be removed from the allowlist so
    # the exception set only ever shrinks.
    stale = _KNOWN_TRANSITIVE_PLATFORM_LEAKS - set(leaks)
    assert not stale, (
        f"these modules no longer leak platform; drop them from the allowlist: {stale}"
    )
