import pytest


def test_clear_namespace_public_api_is_importable():
    from fleetent.vector_store import clear_namespace

    assert callable(clear_namespace)


async def test_in_memory_backend_clear_namespace_removes_only_target_namespace():
    from fleetent.vector_store.backend import InMemoryVectorBackend

    backend = InMemoryVectorBackend()
    await backend.upsert("id-a", [1.0, 0.0], namespace="mem:a")
    await backend.upsert("id-b", [1.0, 0.0], namespace="mem:b")

    await backend.clear_namespace("mem:a")

    assert await backend.search([1.0, 0.0], namespace="mem:a") == []
    assert [result.id for result in await backend.search([1.0, 0.0], namespace="mem:b")] == ["id-b"]


async def test_runtime_clear_namespace_rejects_empty_namespace():
    from fleetent.vector_store import clear_namespace

    with pytest.raises(ValueError, match="namespace must not be empty"):
        await clear_namespace(" ")
