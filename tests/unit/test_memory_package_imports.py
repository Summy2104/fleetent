import ast
import importlib
import sys
from pathlib import Path

import pytest

PUBLIC_MEMORY_NAMES = (
    "MemoryType",
    "MemoryItem",
    "MemoryMaintenancePolicy",
    "MemoryCompactionCandidate",
    "MemoryMaintenanceSummary",
    "extract_and_update",
    "search",
    "update_user_memory_content",
    "mark_user_memory_stale",
    "delete_user_memory",
    "merge_user_memories",
    "iter_indexable_memories",
    "run_memory_maintenance",
)


def test_canonical_memory_package_exports_public_api() -> None:
    memory = importlib.import_module("fleetent.memory")

    for name in PUBLIC_MEMORY_NAMES:
        assert getattr(memory, name)


def test_legacy_memory_layer_module_is_not_importable() -> None:
    sys.modules.pop("fleetent.memory_layer", None)

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fleetent.memory_layer")


def test_long_term_ctx_top_level_package_is_importable() -> None:
    importlib.import_module("fleetent.long_term_ctx")


def test_memory_and_long_term_ctx_do_not_import_platform_modules() -> None:
    for package_name in (
        "fleetent.memory",
        "fleetent.long_term_ctx",
        "fleetent.long_term_ctx._policy",
    ):
        package = importlib.import_module(package_name)
        if package.__file__ is None:
            continue
        package_path = Path(package.__file__).resolve().parent
        for path in package_path.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith("fleetent.platform"), (
                        f"{package_name} imports platform from {path}: {node.module}"
                    )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("fleetent.platform"), (
                            f"{package_name} imports platform from {path}: {alias.name}"
                        )


def test_memory_longterm_ctx_layer_separation() -> None:
    package = importlib.import_module("fleetent.memory")
    if package.__file__ is None:
        pytest.fail("legacy memory package missing __file__")
    package_path = Path(package.__file__).resolve().parent
    for path in package_path.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("fleetent.long_term_ctx"), (
                    f"memory package imports long_term_ctx in {path}: {node.module}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("fleetent.long_term_ctx"), (
                        f"memory package imports long_term_ctx in {path}: {alias.name}"
                    )


def test_long_term_ctx_memory_shim_remains_compatible() -> None:
    pass


def test_long_term_ctx_top_level_package_contains_policy() -> None:
    policy = importlib.import_module("fleetent.long_term_ctx._policy")
    assert policy.__name__ == "fleetent.long_term_ctx._policy"


def test_runtime_loop_imports_long_term_ctx_from_top_level() -> None:
    runtime_loop = importlib.import_module("fleetent.runtime.loop")
    if runtime_loop.__file__ is None:
        raise RuntimeError("runtime.loop module file missing")
    runtime_loop_path = Path(runtime_loop.__file__).resolve()
    runtime_tree = ast.parse(runtime_loop_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(runtime_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "fleetent.long_term_ctx" in imported_modules
    assert "fleetent.intelligence.long_term_ctx" not in imported_modules
