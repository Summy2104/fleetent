import inspect


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


def test_legacy_memory_layer_reexports_canonical_public_api_objects():
    from fleetent import memory_layer
    from fleetent.intelligence import memory

    public_names = {
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
        assert getattr(memory_layer, name) is getattr(memory, name)


def test_legacy_memory_layer_is_thin_public_api_shim():
    from fleetent import memory_layer

    source = inspect.getsource(memory_layer)

    assert "create_database" not in source
    assert "get_async_client_and_config" not in source
    assert "vector_store" not in source
    assert "def _" not in source
