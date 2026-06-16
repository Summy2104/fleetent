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
# of them could leak a ``fleetent.platform`` dependency transitively without tripping
# the direct check. This set pins any *currently known* leaks so NEW transitive leaks
# fail the build immediately; the ratchet test also fails if a pinned module stops
# leaking, forcing this set to shrink as the leaks get fixed.
_KNOWN_TRANSITIVE_PLATFORM_LEAKS: set[str] = set()


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
        f"fleetent.audit_log must be at the top-level src/fleetent/audit_log.py, got {located}"
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
        "fleetent.audit_log imports fleetent.platform, violating its infrastructure-only boundary"
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


def test_cron_scheduler_does_not_depend_on_user_store() -> None:
    """Fire-time principal resolution is injection-decoupled (decouple-cron-principal-recheck).

    cron_scheduler must not reach the platform management DB to resolve a fired task's
    principal — it must not import fleetent.user_store. The blocked/deleted recheck is
    supplied by the platform via set_principal_resolver; standalone trusts the IM identity.
    """
    import importlib

    module = importlib.import_module("fleetent.cron_scheduler")
    assert module.__file__ is not None
    located = Path(module.__file__)
    tree = ast.parse(located.read_text(encoding="utf-8"), filename=str(located))
    imported_modules = set(_iter_imported_modules(tree))

    assert not _is_imported_from(["fleetent.user_store"], imported_modules), (
        "fleetent.cron_scheduler imports fleetent.user_store; fire-time principal "
        "resolution must be injection-decoupled (set_principal_resolver), not a direct "
        "management-DB lookup"
    )
    assert not _is_imported_from(["fleetent.platform"], imported_modules), (
        "fleetent.cron_scheduler imports fleetent.platform, violating agent⊥platform"
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


# ---------------------------------------------------------------------------
# Plane boundary guardrails (核 + 4面 architecture)
# ---------------------------------------------------------------------------

# 核（core）module prefixes — must not import any 面 (face) namespace
_CORE_MODULE_PREFIXES = (
    "fleetent.runtime",
    "fleetent.session",
    "fleetent.model",
    "fleetent.tools",
    "fleetent.integrations",
    "fleetent.governance",
    "fleetent.memory",
    "fleetent.long_term_ctx",
    "fleetent.reflection",
    "fleetent.skills",
    "fleetent.knowledge_base.retrieval",
)

# 面（face）namespaces — cores must not import from these
_FACE_NAMESPACES = (
    "fleetent.platform",
    "fleetent.im_gateway",
)

# Modules in 核 that are composition roots / bootstrappers and intentionally
# wire the core to the edge face at app startup. Each entry must shrink as
# the coupling is eliminated.
_KNOWN_CORE_EDGE_EXCEPTIONS: set[str] = {
    # agent_app.py bootstraps standalone agent mode: starts IM supervisors (SlackSupervisor,
    # TelegramSupervisor) from the edge face and redirects im_gateway.access.APPROVALS_PATH.
    # Coupling is intentional at the composition-root level (not core logic).
    "fleetent.runtime.agent_app",
}

# ②控制 face sub-packages (must not import ③ orchestration)
_CONTROL_FACE_PREFIXES = (
    "fleetent.platform.agent_management_console",
    "fleetent.platform.connector_management",
    "fleetent.platform.knowledge_base_management",
    "fleetent.platform.model_provider_management",
    "fleetent.platform.skill_management",
    "fleetent.platform.user_management",
    "fleetent.platform.chat_management",
    "fleetent.platform.askit_console",
    "fleetent.platform.reflection_management",
    "fleetent.platform.admin_cli",
    "fleetent.platform.agent_statistics",
    "fleetent.platform.im_gateway_management",
)

# ③编排 face sub-packages (must not import ②控制 subpackages)
_ORCHESTRATION_FACE_PREFIXES = ("fleetent.platform.agent_lifecycle",)

# ④摄取 face sub-packages
_INGEST_FACE_PREFIXES = ("fleetent.knowledge_base.ingest",)

# ①边缘 face sub-packages
_EDGE_FACE_PREFIXES = ("fleetent.im_gateway",)

# Pairs (source_prefix, forbidden_target_prefix) — cross-face violations that have not
# yet been fixed; each entry represents an architectural debt to eliminate.
# Ratchet: if an entry disappears the test will fail, forcing removal from this set.
_KNOWN_PLANE_BOUNDARY_VIOLATIONS: set[tuple[str, str]] = {
    # ③编排.materialize aggregates from all ②控制 stores to build agent.yaml
    # Fix: move materialize/secret_store/credential_slots to platform/ shared level
    ("fleetent.platform.agent_lifecycle.materialize", "fleetent.platform.connector_management"),
    (
        "fleetent.platform.agent_lifecycle.materialize",
        "fleetent.platform.knowledge_base_management",
    ),
    (
        "fleetent.platform.agent_lifecycle.materialize",
        "fleetent.platform.model_provider_management",
    ),
    ("fleetent.platform.agent_lifecycle.materialize", "fleetent.platform.skill_management"),
    # ②控制 modules call ③编排 to trigger re-materialization after store changes
    ("fleetent.platform.skill_management.skill_admin_api", "fleetent.platform.agent_lifecycle"),
    (
        "fleetent.platform.knowledge_base_management.kb_admin_api",
        "fleetent.platform.agent_lifecycle",
    ),
    (
        "fleetent.platform.agent_management_console.agent_admin_api",
        "fleetent.platform.agent_lifecycle",
    ),
}


def _is_core_module(module_name: str) -> bool:
    return any(module_name.startswith(p) for p in _CORE_MODULE_PREFIXES)


def test_core_modules_do_not_import_face_namespaces() -> None:
    """核 modules MUST NOT import face namespaces (platform.* or im_gateway.*)."""
    violations: list[str] = []
    for path in _src_python_paths():
        module_name = _module_name(path)
        if not _is_core_module(module_name):
            continue
        if module_name in _KNOWN_CORE_EDGE_EXCEPTIONS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_modules = set(_iter_imported_modules(tree))
        for face in _FACE_NAMESPACES:
            if _is_imported_from([face], imported_modules):
                violations.append(f"{module_name} → {face}")
    assert not violations, (
        "核 modules import face namespaces, violating core→face boundary:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


def _cross_face_violations() -> list[tuple[str, str]]:
    """Collect all (source_module, forbidden_target_prefix) face-to-face import pairs."""
    violations: list[tuple[str, str]] = []
    for path in _src_python_paths():
        module_name = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_modules = set(_iter_imported_modules(tree))

        # ②控制 → ③编排
        if any(module_name.startswith(p) for p in _CONTROL_FACE_PREFIXES):
            for orch in _ORCHESTRATION_FACE_PREFIXES:
                if _is_imported_from([orch], imported_modules):
                    violations.append((module_name, orch))

        # ③编排 → ②控制
        if any(module_name.startswith(p) for p in _ORCHESTRATION_FACE_PREFIXES):
            for ctrl in _CONTROL_FACE_PREFIXES:
                if _is_imported_from([ctrl], imported_modules):
                    violations.append((module_name, ctrl))

        # ①边缘 → ②控制 or ③编排
        if any(module_name.startswith(p) for p in _EDGE_FACE_PREFIXES):
            for ctrl in _CONTROL_FACE_PREFIXES:
                if _is_imported_from([ctrl], imported_modules):
                    violations.append((module_name, ctrl))
            for orch in _ORCHESTRATION_FACE_PREFIXES:
                if _is_imported_from([orch], imported_modules):
                    violations.append((module_name, orch))

    return violations


def test_no_new_plane_boundary_violations() -> None:
    """面①②③④ MUST NOT directly import each other (no new violations beyond allowlist)."""
    found = _cross_face_violations()

    # Normalise to (module, target_prefix) pairs matching the known-violations format
    new_violations = [
        (src, tgt)
        for src, tgt in found
        if not any(
            src.startswith(known_src) and tgt.startswith(known_tgt)
            for known_src, known_tgt in _KNOWN_PLANE_BOUNDARY_VIOLATIONS
        )
    ]
    assert not new_violations, (
        "New plane boundary violations detected (face→face imports):\n"
        + "\n".join(f"  {src} → {tgt}" for src, tgt in new_violations)
    )

    # Ratchet: a pinned violation that no longer exists must be removed from the set.
    stale = {
        (known_src, known_tgt)
        for known_src, known_tgt in _KNOWN_PLANE_BOUNDARY_VIOLATIONS
        if not any(src.startswith(known_src) and tgt.startswith(known_tgt) for src, tgt in found)
    }
    assert not stale, (
        f"These plane boundary violations no longer exist; remove them from the allowlist: {stale}"
    )


# ---------------------------------------------------------------------------
# Reflection two-way guardrail
# ---------------------------------------------------------------------------


def test_reflection_engine_does_not_import_reflection_management() -> None:
    """reflection/ engine MUST NOT import platform.reflection_management (management API)."""
    violations: list[str] = []
    for path in _src_python_paths():
        module_name = _module_name(path)
        if not module_name.startswith("fleetent.reflection"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_modules = set(_iter_imported_modules(tree))
        if _is_imported_from(["fleetent.platform.reflection_management"], imported_modules):
            violations.append(module_name)
    assert not violations, (
        "reflection engine imports platform.reflection_management (management API), "
        "violating reflection→management boundary: " + ", ".join(violations)
    )


def test_reflection_management_does_not_import_reflection_engine() -> None:
    """platform.reflection_management MUST NOT import fleetent.reflection.reflection (engine)."""
    violations: list[str] = []
    for path in _src_python_paths():
        module_name = _module_name(path)
        if not module_name.startswith("fleetent.platform.reflection_management"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_modules = set(_iter_imported_modules(tree))
        # reflection.store (product store) is allowed; reflection.reflection (engine) is not
        if _is_imported_from(["fleetent.reflection.reflection"], imported_modules):
            violations.append(module_name)
    assert not violations, (
        "platform.reflection_management imports fleetent.reflection.reflection (engine private), "
        "violating management→engine boundary: " + ", ".join(violations)
    )


# ---------------------------------------------------------------------------
# Long-lived async resource owner-task guardrail
# ---------------------------------------------------------------------------
# A long-lived async resource (connection / SDK session / subprocess stream) must be
# owned by a single task: opened and closed on the same task. A module-level
# AsyncExitStack singleton holding such resources is entered by whichever task first uses
# it and unwound by another at shutdown — violating anyio cancel-scope task affinity and
# crashing the process on teardown (2026-06-11). Function-local AsyncExitStack (same-task,
# scoped) is fine; only module-scope holders are flagged.


def _module_level_asyncexitstack_holders(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in tree.body:  # module scope only — not inside any function/class
        if isinstance(node, ast.AnnAssign) and "AsyncExitStack" in ast.dump(node.annotation):
            if isinstance(node.target, ast.Name):
                names.append(node.target.id)
        elif isinstance(node, ast.Assign) and "AsyncExitStack" in ast.dump(node.value):
            names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def test_no_module_level_asyncexitstack_singleton() -> None:
    """No src module may hold a module-level AsyncExitStack singleton (owner-task rule)."""
    offenders: dict[str, list[str]] = {}
    for path in _src_python_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = _module_level_asyncexitstack_holders(tree)
        if names:
            offenders[_module_name(path)] = names
    assert not offenders, (
        "module-level AsyncExitStack singleton(s) holding long-lived async resources — give "
        "each resource a per-session owner task (谁打开谁关闭): " + repr(offenders)
    )


def test_asyncexitstack_guardrail_is_not_vacuous() -> None:
    """Detector catches a planted module-level holder, ignores a function-local one."""
    planted = ast.parse(
        "from contextlib import AsyncExitStack\n_leak: AsyncExitStack | None = None\n"
    )
    assert _module_level_asyncexitstack_holders(planted) == ["_leak"]
    local = ast.parse(
        "from contextlib import AsyncExitStack\n"
        "async def f():\n    async with AsyncExitStack() as s:\n        return s\n"
    )
    assert _module_level_asyncexitstack_holders(local) == []
