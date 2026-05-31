import pytest


def _l2_norm(vector):
    return sum(value * value for value in vector) ** 0.5


def test_public_api_is_importable():
    from fleetent.intelligence.vector_store import (
        SearchResult,
        delete,
        knowledge_namespace,
        memory_namespace,
        search,
        upsert,
    )

    assert SearchResult("id-1", 0.5).id == "id-1"
    assert callable(upsert)
    assert callable(search)
    assert callable(delete)
    assert callable(memory_namespace)
    assert callable(knowledge_namespace)


def test_namespace_helpers_return_fixed_formats():
    from fleetent.intelligence.vector_store import knowledge_namespace, memory_namespace

    assert memory_namespace("u1") == "mem:u1"
    assert knowledge_namespace("default", "global") == "kb:default:global"


@pytest.mark.parametrize(
    ("user_id",),
    [
        ("",),
        ("   ",),
    ],
)
def test_memory_namespace_rejects_empty_user_id(user_id):
    from fleetent.intelligence.vector_store import memory_namespace

    with pytest.raises(ValueError, match="user_id"):
        memory_namespace(user_id)


@pytest.mark.parametrize(
    ("tenant_id", "kb_id", "message"),
    [
        ("", "global", "tenant_id"),
        ("default", "", "kb_id"),
        ("   ", "global", "tenant_id"),
        ("default", "   ", "kb_id"),
    ],
)
def test_knowledge_namespace_rejects_empty_parts(tenant_id, kb_id, message):
    from fleetent.intelligence.vector_store import knowledge_namespace

    with pytest.raises(ValueError, match=message):
        knowledge_namespace(tenant_id, kb_id)


def test_deterministic_embedding_is_stable_with_default_dimensions():
    from fleetent.intelligence.vector_store.embeddings import DeterministicEmbedding

    embedding = DeterministicEmbedding()

    assert embedding.embed("Python debugging") == embedding.embed("Python debugging")
    assert len(embedding.embed("Python debugging")) == 64


def test_deterministic_embedding_normalizes_non_empty_text():
    from fleetent.intelligence.vector_store.embeddings import DeterministicEmbedding

    vector = DeterministicEmbedding().embed("Python debugging")

    assert _l2_norm(vector) == pytest.approx(1.0)


def test_deterministic_embedding_returns_stable_zero_vector_for_empty_text():
    from fleetent.intelligence.vector_store.embeddings import DeterministicEmbedding

    embedding = DeterministicEmbedding(dimensions=4)

    assert embedding.embed("") == [0.0, 0.0, 0.0, 0.0]
    assert embedding.embed("   ") == [0.0, 0.0, 0.0, 0.0]


async def test_upsert_then_search_returns_id_and_score():
    from dataclasses import fields

    from fleetent.intelligence.vector_store import SearchResult, search, upsert

    await upsert("id-1", "python debugging", namespace="mem:user-1")

    results = await search("python debug", namespace="mem:user-1")

    assert [field.name for field in fields(SearchResult)] == ["id", "score"]
    assert "id-1" in [result.id for result in results]
    assert all(isinstance(result.score, float) for result in results)


async def test_search_limit_is_respected():
    from fleetent.intelligence.vector_store import search, upsert

    namespace = "mem:limit-user"
    await upsert("id-1", "alpha python", namespace=namespace)
    await upsert("id-2", "beta python", namespace=namespace)
    await upsert("id-3", "gamma python", namespace=namespace)

    results = await search("python", namespace=namespace, limit=2)

    assert len(results) == 2


async def test_search_does_not_cross_namespaces():
    from fleetent.intelligence.vector_store import search, upsert

    await upsert("id-a", "python debugging", namespace="mem:namespace-a")
    await upsert("id-b", "python debugging", namespace="mem:namespace-b")

    results = await search("python debugging", namespace="mem:namespace-a")

    assert [result.id for result in results] == ["id-a"]


async def test_upsert_same_id_overwrites_without_duplicates():
    from fleetent.intelligence.vector_store import search, upsert

    namespace = "mem:overwrite-user"
    await upsert("same-id", "python debugging", namespace=namespace)
    await upsert("same-id", "incident response", namespace=namespace)

    results = await search("incident response", namespace=namespace)

    assert [result.id for result in results] == ["same-id"]
    assert results[0].score > 0


async def test_delete_removes_vector_from_namespace():
    from fleetent.intelligence.vector_store import delete, search, upsert

    namespace = "mem:delete-user"
    await upsert("id-1", "python debugging", namespace=namespace)

    await delete("id-1", namespace=namespace)

    assert await search("python debugging", namespace=namespace) == []


async def test_search_sorts_by_score_descending_then_id_ascending():
    from fleetent.intelligence.vector_store.backend import InMemoryVectorBackend

    backend = InMemoryVectorBackend()
    await backend.upsert("b", [1.0, 0.0], namespace="mem:ordering")
    await backend.upsert("a", [1.0, 0.0], namespace="mem:ordering")
    await backend.upsert("c", [0.5, 0.5], namespace="mem:ordering")

    results = await backend.search([1.0, 0.0], namespace="mem:ordering")

    assert [result.id for result in results] == ["a", "b", "c"]


def test_unsupported_vector_backend_fails_fast():
    from fleetent.config import VectorStoreSettings
    from fleetent.intelligence.vector_store.backend import create_vector_backend

    with pytest.raises(ValueError, match="Unsupported vector_store.backend 'qdrant'.*memory"):
        create_vector_backend(VectorStoreSettings(backend="qdrant"))


def test_unsupported_embedding_backend_fails_fast():
    from fleetent.config import EmbeddingSettings
    from fleetent.intelligence.vector_store.embeddings import create_embedding_backend

    with pytest.raises(ValueError, match="Unsupported embedding.backend 'bge-m3'.*deterministic"):
        create_embedding_backend(EmbeddingSettings(backend="bge-m3"))
