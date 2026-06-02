def _sqlite_database_url(path):
    return f"sqlite:///{path}"


async def test_sqlite_backend_clear_namespace_removes_only_target_namespace(tmp_path):
    from fleetent.intelligence.vector_store.backend import SQLiteVectorBackend

    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(tmp_path / "vectors.db"))
    await backend.upsert("id-a", [1.0, 0.0], namespace="mem:a")
    await backend.upsert("id-b", [1.0, 0.0], namespace="mem:b")

    await backend.clear_namespace("mem:a")

    assert await backend.search([1.0, 0.0], namespace="mem:a") == []
    assert [result.id for result in await backend.search([1.0, 0.0], namespace="mem:b")] == ["id-b"]


async def test_sqlite_backend_clear_namespace_is_idempotent(tmp_path):
    from fleetent.intelligence.vector_store.backend import SQLiteVectorBackend

    backend = SQLiteVectorBackend(database_url=_sqlite_database_url(tmp_path / "vectors.db"))

    await backend.clear_namespace("mem:missing")
    await backend.clear_namespace("mem:missing")

    assert await backend.search([1.0, 0.0], namespace="mem:missing") == []
