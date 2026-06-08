import ast
import importlib
from pathlib import Path
import sys

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
    for package_name in ("fleetent.memory", "fleetent.long_term_ctx", "fleetent.long_term_ctx._policy"):
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
    package = importlib.import_module("fleetent.intelligence.memory")
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
    import fleetent
    from fleetent.intelligence import long_term_ctx as legacy_long_term_ctx
    from fleetent.intelligence import memory as legacy_memory
    from fleetent import long_term_ctx, memory

    assert legacy_long_term_ctx is long_term_ctx
    assert legacy_memory is memory
