import importlib
import sys

import pytest


def test_canonical_memory_package_exports_public_api():
    from fleetent.intelligence import memory

    public_names = {
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
    }

    for name in public_names:
        assert hasattr(memory, name)


def test_legacy_memory_layer_is_removed():
    sys.modules.pop("fleetent.memory_layer", None)

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fleetent.memory_layer")
