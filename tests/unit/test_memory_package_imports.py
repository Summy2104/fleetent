import importlib
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
    memory = importlib.import_module("fleetent.intelligence.memory")

    for name in PUBLIC_MEMORY_NAMES:
        assert getattr(memory, name)


def test_legacy_memory_layer_module_is_not_importable() -> None:
    sys.modules.pop("fleetent.memory_layer", None)

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fleetent.memory_layer")
