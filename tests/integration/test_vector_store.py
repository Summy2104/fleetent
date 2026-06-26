import pytest

from fleetent.agent_config import (
    AgentFile,
    AgentModels,
    ModelRouteEntry,
    ModelTarget,
    default_models,
)


def _sqlite_database_url(path):
    return f"sqlite:///{path}"


def _l2_norm(vector):
    return sum(value * value for value in vector) ** 0.5


def _agent(**fields):
    return AgentFile(name="t", version=1, models=default_models(), **fields)


def _neutral_agent():
    return AgentFile(name="", version=0, models=default_models())


def _http_embedding_models(endpoint: str) -> AgentModels:
    return AgentModels(
        targets=[
            ModelTarget(
                id="embed",
                provider="test",
                protocol="http_embedding",
                endpoint=endpoint,
                model="bge-m3",
                params={"dimensions": 2},
            )
        ],
        routes={"embedding": [ModelRouteEntry(target="embed")]},
    )


def test_public_api_is_importable():
    from fleetent.vector_store import (
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
    from fleetent.vector_store import (
        agent_memory_namespace,
        knowledge_namespace,
        memory_namespace,
    )

    assert memory_namespace("u1") == "mem:u1"
    assert agent_memory_namespace() == "agentmem:"
    assert knowledge_namespace("default", "global") == "kb:default:global"


def test_memory_namespace_single_param_returns_user_scoped():
    from fleetent.vector_store import memory_namespace

    assert memory_namespace("u1") == "mem:u1"
    assert memory_namespace("alice") == "mem:alice"


def test_memory_namespace_two_arg_raises_type_error():
    import pytest

    from fleetent.vector_store import memory_namespace

    with pytest.raises(TypeError):
        memory_namespace("u1", "analyst")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("user_id",),
    [
        ("",),
        ("   ",),
    ],
)
def test_memory_namespace_rejects_empty_user_id(user_id):
    from fleetent.vector_store import memory_namespace

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
    from fleetent.vector_store import knowledge_namespace

    with pytest.raises(ValueError, match=message):
        knowledge_namespace(tenant_id, kb_id)


async def test_deterministic_embedding_is_stable_with_default_dimensions():
    from fleetent.vector_store.embeddings import DeterministicEmbedding

    embedding = DeterministicEmbedding()

    assert await embedding.embed("Python debugging") == await embedding.embed("Python debugging")
    assert len(await embedding.embed("Python debugging")) == 64


async def test_deterministic_embedding_normalizes_non_empty_text():
    from fleetent.vector_store.embeddings import DeterministicEmbedding

    vector = await DeterministicEmbedding().embed("Python debugging")

    assert _l2_norm(vector) == pytest.approx(1.0)


async def test_deterministic_embedding_returns_stable_zero_vector_for_empty_text():
    from fleetent.vector_store.embeddings import DeterministicEmbedding

    embedding = DeterministicEmbedding(dimensions=4)

    assert await embedding.embed("") == [0.0, 0.0, 0.0, 0.0]
    assert await embedding.embed("   ") == [0.0, 0.0, 0.0, 0.0]


async def test_upsert_then_search_returns_id_and_score():
    from dataclasses import fields

    from fleetent.vector_store import SearchResult, search, upsert

    await upsert("id-1", "python debugging", namespace="mem:user-1")

    results = await search("python debug", namespace="mem:user-1")

    assert [field.name for field in fields(SearchResult)] == ["id", "score"]
    assert "id-1" in [result.id for result in results]
    assert all(isinstance(result.score, float) for result in results)


async def test_upsert_uses_configured_http_embedding_provider():
    import httpx
    import respx

    from fleetent.vector_store import runtime
    from fleetent.vector_store.backend import InMemoryVectorBackend

    endpoint = "http://runtime-embedding.test/v1/upsert-embeddings"
    runtime._configure(
        AgentFile(
            name="t",
            version=1,
            models=_http_embedding_models(endpoint),
        )
    )

    try:
        with respx.mock:
            route = respx.post(endpoint).mock(
                return_value=httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0]}]})
            )

            await runtime.upsert("id-http", "python debugging", namespace="mem:http-upsert")

        assert route.called
        assert isinstance(runtime._backend, InMemoryVectorBackend)
        assert runtime._backend._vectors["mem:http-upsert"]["id-http"] == [1.0, 0.0]
    finally:
        runtime._configure(_neutral_agent())


async def test_search_uses_configured_http_embedding_provider():
    import httpx
    import respx

    from fleetent.vector_store import runtime

    endpoint = "http://runtime-embedding.test/v1/search-embeddings"
    runtime._configure(
        AgentFile(
            name="t",
            version=1,
            models=_http_embedding_models(endpoint),
        )
    )

    try:
        with respx.mock:
            route = respx.post(endpoint).mock(
                return_value=httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0]}]})
            )

            await runtime.upsert("id-http", "stored text", namespace="mem:http-search")
            results = await runtime.search("query text", namespace="mem:http-search")

        assert route.call_count == 2
        assert [result.id for result in results] == ["id-http"]
    finally:
        runtime._configure(_neutral_agent())


async def test_search_limit_is_respected():
    from fleetent.vector_store import search, upsert

    namespace = "mem:limit-user"
    await upsert("id-1", "alpha python", namespace=namespace)
    await upsert("id-2", "beta python", namespace=namespace)
    await upsert("id-3", "gamma python", namespace=namespace)

    results = await search("python", namespace=namespace, limit=2)

    assert len(results) == 2


async def test_search_does_not_cross_namespaces():
    from fleetent.vector_store import search, upsert

    await upsert("id-a", "python debugging", namespace="mem:namespace-a")
    await upsert("id-b", "python debugging", namespace="mem:namespace-b")

    results = await search("python debugging", namespace="mem:namespace-a")

    assert [result.id for result in results] == ["id-a"]


async def test_upsert_same_id_overwrites_without_duplicates():
    from fleetent.vector_store import search, upsert

    namespace = "mem:overwrite-user"
    await upsert("same-id", "python debugging", namespace=namespace)
    await upsert("same-id", "incident response", namespace=namespace)

    results = await search("incident response", namespace=namespace)

    assert [result.id for result in results] == ["same-id"]
    assert results[0].score > 0


async def test_delete_removes_vector_from_namespace():
    from fleetent.vector_store import delete, search, upsert

    namespace = "mem:delete-user"
    await upsert("id-1", "python debugging", namespace=namespace)

    await delete("id-1", namespace=namespace)

    assert await search("python debugging", namespace=namespace) == []


async def test_search_sorts_by_score_descending_then_id_ascending():
    from fleetent.vector_store.backend import InMemoryVectorBackend

    backend = InMemoryVectorBackend()
    await backend.upsert("b", [1.0, 0.0], namespace="mem:ordering")
    await backend.upsert("a", [1.0, 0.0], namespace="mem:ordering")
    await backend.upsert("c", [0.5, 0.5], namespace="mem:ordering")

    results = await backend.search([1.0, 0.0], namespace="mem:ordering")

    assert [result.id for result in results] == ["a", "b", "c"]


def test_unsupported_vector_backend_fails_fast():
    from fleetent.config import VectorStoreSettings
    from fleetent.vector_store.backend import create_vector_backend

    with pytest.raises(ValueError, match="Unsupported vector_store.backend 'qdrant'.*memory"):
        create_vector_backend(VectorStoreSettings(backend="qdrant"))


def test_unsupported_embedding_backend_fails_fast():
    from fleetent.config import EmbeddingSettings
    from fleetent.vector_store.embeddings import create_embedding_backend

    with pytest.raises(ValueError, match="Unsupported embedding.backend 'bge-m3'.*deterministic"):
        create_embedding_backend(EmbeddingSettings(backend="bge-m3"))


async def test_sqlite_backend_first_use_creates_vector_items_schema(tmp_path):
    import aiosqlite

    from fleetent.vector_store.backend import SQLiteVectorBackend

    database_path = tmp_path / "vectors.db"
    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(database_path))

    await backend.upsert("id-1", [1.0, 0.0], namespace="mem:user-1")

    async with aiosqlite.connect(database_path) as db:
        columns = await db.execute_fetchall("PRAGMA table_info(vector_items)")
        indexes = await db.execute_fetchall("PRAGMA index_list(vector_items)")

    assert {column[1] for column in columns} == {
        "namespace",
        "id",
        "dimensions",
        "vector_json",
        "updated_at",
    }
    assert any(index[1] == "idx_vector_items_namespace" for index in indexes)


async def test_sqlite_backend_persists_vectors_across_backend_instances(tmp_path):
    from fleetent.vector_store.backend import SQLiteVectorBackend

    database_url = _sqlite_database_url(tmp_path / "vectors.db")
    await SQLiteVectorBackend(database_url=database_url).upsert(
        "id-1", [1.0, 0.0], namespace="mem:user-1"
    )

    results = await SQLiteVectorBackend(database_url=database_url).search(
        [1.0, 0.0], namespace="mem:user-1"
    )

    assert [result.id for result in results] == ["id-1"]


async def test_sqlite_backend_overwrites_same_namespace_and_id(tmp_path):
    import aiosqlite

    from fleetent.vector_store.backend import SQLiteVectorBackend

    database_path = tmp_path / "vectors.db"
    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(database_path))

    await backend.upsert("same-id", [1.0, 0.0], namespace="mem:user-1")
    await backend.upsert("same-id", [0.0, 1.0], namespace="mem:user-1")

    results = await backend.search([0.0, 1.0], namespace="mem:user-1")
    async with aiosqlite.connect(database_path) as db:
        count_rows = await db.execute_fetchall(
            "SELECT COUNT(*) FROM vector_items WHERE namespace = :namespace AND id = :id",
            {"namespace": "mem:user-1", "id": "same-id"},
        )

    assert [result.id for result in results] == ["same-id"]
    assert count_rows[0][0] == 1


async def test_sqlite_backend_search_is_namespace_scoped(tmp_path):
    from fleetent.vector_store.backend import SQLiteVectorBackend

    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(tmp_path / "vectors.db"))
    await backend.upsert("id-a", [1.0, 0.0], namespace="mem:a")
    await backend.upsert("id-b", [1.0, 0.0], namespace="mem:b")

    results = await backend.search([1.0, 0.0], namespace="mem:a")

    assert [result.id for result in results] == ["id-a"]


async def test_sqlite_backend_search_respects_limit(tmp_path):
    from fleetent.vector_store.backend import SQLiteVectorBackend

    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(tmp_path / "vectors.db"))
    await backend.upsert("id-1", [1.0, 0.0], namespace="mem:user-1")
    await backend.upsert("id-2", [0.9, 0.1], namespace="mem:user-1")

    assert await backend.search([1.0, 0.0], namespace="mem:user-1", limit=0) == []
    assert len(await backend.search([1.0, 0.0], namespace="mem:user-1", limit=1)) == 1


async def test_sqlite_backend_delete_is_namespace_scoped(tmp_path):
    from fleetent.vector_store.backend import SQLiteVectorBackend

    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(tmp_path / "vectors.db"))
    await backend.upsert("same-id", [1.0, 0.0], namespace="mem:a")
    await backend.upsert("same-id", [1.0, 0.0], namespace="mem:b")

    await backend.delete("same-id", namespace="mem:a")

    assert await backend.search([1.0, 0.0], namespace="mem:a") == []
    assert [result.id for result in await backend.search([1.0, 0.0], namespace="mem:b")] == [
        "same-id"
    ]


async def test_sqlite_backend_search_sorts_by_score_desc_then_id_asc(tmp_path):
    from fleetent.vector_store.backend import SQLiteVectorBackend

    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(tmp_path / "vectors.db"))
    await backend.upsert("b", [1.0, 0.0], namespace="mem:ordering")
    await backend.upsert("a", [1.0, 0.0], namespace="mem:ordering")
    await backend.upsert("c", [0.0, 1.0], namespace="mem:ordering")

    results = await backend.search([1.0, 0.0], namespace="mem:ordering")

    assert [result.id for result in results] == ["a", "b", "c"]


async def test_sqlite_backend_search_skips_dimension_mismatch(tmp_path):
    from fleetent.vector_store.backend import SQLiteVectorBackend

    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(tmp_path / "vectors.db"))
    await backend.upsert("valid", [1.0, 0.0], namespace="mem:user-1")
    await backend.upsert("wrong-dimension", [1.0, 0.0, 0.0], namespace="mem:user-1")

    results = await backend.search([1.0, 0.0], namespace="mem:user-1")

    assert [result.id for result in results] == ["valid"]


async def test_sqlite_backend_search_skips_corrupt_vector_json(tmp_path):
    import aiosqlite

    from fleetent.vector_store.backend import SQLiteVectorBackend

    database_path = tmp_path / "vectors.db"
    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(database_path))
    await backend.upsert("valid", [1.0, 0.0], namespace="mem:user-1")

    async with aiosqlite.connect(database_path) as db:
        await db.execute(
            """
            INSERT INTO vector_items (namespace, id, dimensions, vector_json, updated_at)
            VALUES (:namespace, :id, :dimensions, :vector_json, CURRENT_TIMESTAMP)
            """,
            {
                "namespace": "mem:user-1",
                "id": "corrupt",
                "dimensions": 2,
                "vector_json": "not-json",
            },
        )
        await db.commit()

    results = await backend.search([1.0, 0.0], namespace="mem:user-1")

    assert [result.id for result in results] == ["valid"]


async def test_sqlite_backend_upsert_rejects_empty_vector(tmp_path):
    from fleetent.vector_store.backend import SQLiteVectorBackend

    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(tmp_path / "vectors.db"))

    with pytest.raises(ValueError, match="vector must not be empty"):
        await backend.upsert("id-1", [], namespace="mem:user-1")


async def test_runtime_public_api_uses_sqlite_backend_with_global_database_url(
    tmp_path, monkeypatch
):
    from fleetent.vector_store import runtime
    from fleetent.vector_store.backend import create_vector_backend

    agent = _agent(vector_store={"backend": "sqlite"})
    database_url = _sqlite_database_url(tmp_path / "vectors.db")
    monkeypatch.setattr(
        runtime, "_backend", create_vector_backend(agent.vector_store, database_url=database_url)
    )

    await runtime.upsert("id-1", "python debugging", namespace="mem:user-1")
    assert [result.id for result in await runtime.search("python", namespace="mem:user-1")] == [
        "id-1"
    ]

    await runtime.delete("id-1", namespace="mem:user-1")
    assert await runtime.search("python", namespace="mem:user-1") == []
