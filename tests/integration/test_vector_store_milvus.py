"""Contract tests for the Milvus vector backend.

Integration layer, not unit: Milvus Lite writes a real database file and manages real
collection schema, which the project's test-layering rule keeps out of ``tests/unit``.

The backend must satisfy the same ``VectorBackend`` protocol as the SQLite one, so most
cases here mirror ``test_vector_store.py``. The Milvus-specific risks get their own cases:
string primary keys (chunk ids are UUIDs, Milvus defaults to int64), namespaces containing
``:`` (``kb:{tenant}:{kb_id}`` is not a legal collection name, so namespace isolation has to
ride on a partition key), and the fixed collection dimension (the protocol's ``upsert`` does
not carry one, so it must be inferred from the first vector).
"""

import pytest

pytest.importorskip("pymilvus", reason="Milvus backend requires pymilvus[milvus_lite]")


def _milvus_url(path) -> str:
    return f"milvus:///{path}"


def _backend(tmp_path, name: str = "vectors.db"):
    from fleetent.vector_store.backend import MilvusVectorBackend

    return MilvusVectorBackend(database_url=_milvus_url(tmp_path / name))


# ── VectorBackend protocol contract (mirrors the SQLite backend's cases) ──


async def test_upsert_then_search_returns_id_and_score(tmp_path) -> None:
    backend = _backend(tmp_path)

    await backend.upsert("id-a", [1.0, 0.0], namespace="mem:u1")
    results = await backend.search([1.0, 0.0], namespace="mem:u1")

    assert [result.id for result in results] == ["id-a"]
    assert results[0].score == pytest.approx(1.0, abs=1e-5)


async def test_search_does_not_cross_namespaces(tmp_path) -> None:
    backend = _backend(tmp_path)

    await backend.upsert("id-a", [1.0, 0.0], namespace="mem:u1")
    await backend.upsert("id-b", [1.0, 0.0], namespace="mem:u2")

    assert [r.id for r in await backend.search([1.0, 0.0], namespace="mem:u1")] == ["id-a"]
    assert [r.id for r in await backend.search([1.0, 0.0], namespace="mem:u2")] == ["id-b"]


async def test_upsert_same_id_overwrites_without_duplicates(tmp_path) -> None:
    backend = _backend(tmp_path)

    await backend.upsert("id-a", [1.0, 0.0], namespace="mem:u1")
    await backend.upsert("id-a", [0.0, 1.0], namespace="mem:u1")

    results = await backend.search([0.0, 1.0], namespace="mem:u1")

    assert [result.id for result in results] == ["id-a"]
    assert results[0].score == pytest.approx(1.0, abs=1e-5)


async def test_search_limit_is_respected(tmp_path) -> None:
    backend = _backend(tmp_path)

    for index in range(5):
        await backend.upsert(f"id-{index}", [1.0, float(index)], namespace="mem:u1")

    assert len(await backend.search([1.0, 0.0], namespace="mem:u1", limit=2)) == 2


async def test_search_sorts_by_score_descending(tmp_path) -> None:
    backend = _backend(tmp_path)

    await backend.upsert("far", [0.0, 1.0], namespace="mem:u1")
    await backend.upsert("near", [1.0, 0.0], namespace="mem:u1")

    results = await backend.search([1.0, 0.0], namespace="mem:u1")

    assert [result.id for result in results] == ["near", "far"]
    assert results[0].score >= results[1].score


async def test_delete_removes_vector_from_namespace(tmp_path) -> None:
    backend = _backend(tmp_path)

    await backend.upsert("id-a", [1.0, 0.0], namespace="mem:u1")
    await backend.delete("id-a", namespace="mem:u1")

    assert await backend.search([1.0, 0.0], namespace="mem:u1") == []


async def test_clear_namespace_removes_only_target_namespace(tmp_path) -> None:
    backend = _backend(tmp_path)

    await backend.upsert("id-a", [1.0, 0.0], namespace="mem:a")
    await backend.upsert("id-b", [1.0, 0.0], namespace="mem:b")

    await backend.clear_namespace("mem:a")

    assert await backend.search([1.0, 0.0], namespace="mem:a") == []
    assert [r.id for r in await backend.search([1.0, 0.0], namespace="mem:b")] == ["id-b"]


async def test_clear_namespace_is_idempotent(tmp_path) -> None:
    backend = _backend(tmp_path)

    await backend.clear_namespace("mem:missing")
    await backend.clear_namespace("mem:missing")

    assert await backend.search([1.0, 0.0], namespace="mem:missing") == []


async def test_search_on_unseen_namespace_returns_empty(tmp_path) -> None:
    """No collection exists yet; the backend must answer empty rather than raise."""
    backend = _backend(tmp_path)

    assert await backend.search([1.0, 0.0], namespace="kb:acme:global") == []


async def test_search_with_non_positive_limit_returns_empty(tmp_path) -> None:
    backend = _backend(tmp_path)

    await backend.upsert("id-a", [1.0, 0.0], namespace="mem:u1")

    assert await backend.search([1.0, 0.0], namespace="mem:u1", limit=0) == []


async def test_upsert_rejects_empty_vector(tmp_path) -> None:
    backend = _backend(tmp_path)

    with pytest.raises(ValueError, match="vector must not be empty"):
        await backend.upsert("id-a", [], namespace="mem:u1")


async def test_persists_vectors_across_backend_instances(tmp_path) -> None:
    """Milvus Lite is file-backed; a new client on the same URI must see prior writes."""
    await _backend(tmp_path).upsert("id-a", [1.0, 0.0], namespace="mem:u1")

    results = await _backend(tmp_path).search([1.0, 0.0], namespace="mem:u1")

    assert [result.id for result in results] == ["id-a"]


# ── Milvus-specific risks ──


async def test_preserves_string_primary_keys(tmp_path) -> None:
    """Chunk ids are UUID strings; Milvus defaults to an int64 primary key."""
    chunk_id = "3f2b1c8e-9a4d-4c7f-8b21-0e5d6a7c9f10"
    backend = _backend(tmp_path)

    await backend.upsert(chunk_id, [1.0, 0.0], namespace="kb:acme:global")

    assert [r.id for r in await backend.search([1.0, 0.0], namespace="kb:acme:global")] == [
        chunk_id
    ]


async def test_isolates_knowledge_namespaces_containing_colons(tmp_path) -> None:
    """``kb:{tenant}:{kb_id}`` is not a legal Milvus collection name.

    Isolation therefore has to ride on a partition key inside one collection, and it must hold
    across tenants — this is the multi-tenant boundary, so a leak here is a data-isolation bug,
    not a ranking bug.
    """
    backend = _backend(tmp_path)

    await backend.upsert("acme-doc", [1.0, 0.0], namespace="kb:acme:global")
    await backend.upsert("globex-doc", [1.0, 0.0], namespace="kb:globex:global")

    acme = await backend.search([1.0, 0.0], namespace="kb:acme:global")
    globex = await backend.search([1.0, 0.0], namespace="kb:globex:global")

    assert [r.id for r in acme] == ["acme-doc"]
    assert [r.id for r in globex] == ["globex-doc"]


async def test_same_id_in_two_namespaces_coexists(tmp_path) -> None:
    """Parity with the SQLite backend, whose primary key is ``(namespace, id)``.

    Milvus offers a single primary-key field, so a naive mapping of ``id`` onto it would let a
    write in one namespace silently destroy another tenant's row. The key must be derived from
    both parts.
    """
    backend = _backend(tmp_path)

    await backend.upsert("shared-id", [1.0, 0.0], namespace="kb:acme:global")
    await backend.upsert("shared-id", [0.0, 1.0], namespace="kb:globex:global")

    acme = await backend.search([1.0, 0.0], namespace="kb:acme:global")
    globex = await backend.search([0.0, 1.0], namespace="kb:globex:global")

    assert [r.id for r in acme] == ["shared-id"]
    assert [r.id for r in globex] == ["shared-id"]
    assert acme[0].score == pytest.approx(1.0, abs=1e-5)
    assert globex[0].score == pytest.approx(1.0, abs=1e-5)


async def test_delete_only_affects_the_given_namespace(tmp_path) -> None:
    backend = _backend(tmp_path)

    await backend.upsert("shared-id", [1.0, 0.0], namespace="kb:acme:global")
    await backend.upsert("shared-id", [1.0, 0.0], namespace="kb:globex:global")

    await backend.delete("shared-id", namespace="kb:acme:global")

    assert await backend.search([1.0, 0.0], namespace="kb:acme:global") == []
    assert [r.id for r in await backend.search([1.0, 0.0], namespace="kb:globex:global")] == [
        "shared-id"
    ]


async def test_rejects_dimension_change_after_collection_exists(tmp_path) -> None:
    """The collection dimension is fixed at creation, so a mismatch must fail loudly.

    The SQLite backend can afford to store any width and skip mismatches at search time;
    Milvus cannot, and silently dropping the write would leave a chunk unsearchable with no
    signal. Fail fast instead.
    """
    backend = _backend(tmp_path)

    await backend.upsert("id-a", [1.0, 0.0], namespace="mem:u1")

    with pytest.raises(ValueError, match="dimension"):
        await backend.upsert("id-b", [1.0, 0.0, 0.0], namespace="mem:u1")


# ── factory wiring ──


def test_factory_creates_milvus_backend_from_settings(tmp_path) -> None:
    from fleetent.config import VectorStoreSettings
    from fleetent.vector_store.backend import MilvusVectorBackend, create_vector_backend

    backend = create_vector_backend(
        VectorStoreSettings(backend="milvus"),
        database_url=_milvus_url(tmp_path / "vectors.db"),
    )

    assert isinstance(backend, MilvusVectorBackend)


def test_factory_rejects_milvus_without_database_url() -> None:
    from fleetent.config import VectorStoreSettings
    from fleetent.vector_store.backend import create_vector_backend

    with pytest.raises(ValueError, match="milvus"):
        create_vector_backend(VectorStoreSettings(backend="milvus"), database_url=None)
