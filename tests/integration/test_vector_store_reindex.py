import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta

from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


def _patch_memory_database(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def _insert_memory_row(
    db_path,
    *,
    id: str,
    user_id: str = "alice",
    type: str = "identity",
    content: str,
    expires_at: str | None = None,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, user_id, type, content, now, now, expires_at),
        )


def _configure_memory_vector_runtime(monkeypatch):
    from fleetent.agent_config import AgentFile, default_models
    from fleetent.vector_store import runtime

    runtime._configure(
        AgentFile(
            name="",
            version=0,
            models=default_models(),
            vector_store={"backend": "memory"},
        )
    )


def test_memory_rebuild_removes_stale_vectors_and_indexes_current_items(tmp_path, monkeypatch):
    from fleetent.vector_store import ReindexRequest, reindex, search, upsert

    db_path = _patch_memory_database(tmp_path, monkeypatch)
    _configure_memory_vector_runtime(monkeypatch)
    _insert_memory_row(
        db_path,
        id="mem-current",
        content="User likes Python debugging",
    )
    _insert_memory_row(
        db_path,
        id="mem-expired",
        type="context",
        content="User works on old billing migration",
        expires_at=(datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)).isoformat(),
    )
    asyncio.run(upsert("mem-stale", "User likes stale vectors", namespace="mem:alice"))
    asyncio.run(upsert("other-user", "Other user memory", namespace="mem:bob"))

    summary = reindex(ReindexRequest(owner="memory", user_id="alice"))

    alice_results = asyncio.run(search("User likes Python debugging", namespace="mem:alice"))
    bob_results = asyncio.run(search("Other user memory", namespace="mem:bob"))
    assert summary.scanned == 1
    assert summary.reindexed == 1
    assert summary.failed == 0
    assert [result.id for result in alice_results] == ["mem-current"]
    assert [result.id for result in bob_results] == ["other-user"]


def _patch_knowledge_runtime(monkeypatch, tmp_path):
    from fleetent.config import KnowledgeBaseSettings
    from fleetent.intelligence.knowledge_base import runtime as knowledge_runtime

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(knowledge_runtime, "_database", lambda: database)
    monkeypatch.setattr(
        knowledge_runtime,
        "_kb_config",
        lambda: KnowledgeBaseSettings(chunk_size=100, chunk_overlap=0),
    )
    return knowledge_runtime


def test_knowledge_base_rebuild_removes_stale_vectors_and_indexes_current_chunks(
    tmp_path, monkeypatch
):
    from fleetent.vector_store import ReindexRequest, reindex, search, upsert

    knowledge_runtime = _patch_knowledge_runtime(monkeypatch, tmp_path)
    _configure_memory_vector_runtime(monkeypatch)
    document = asyncio.run(
        knowledge_runtime.ingest_text(
            filename="guide.txt",
            content="Tenant handbook covers Python debugging",
            tenant_id="tenant-a",
            kb_id="global",
        )
    )
    asyncio.run(
        knowledge_runtime.ingest_text(
            filename="other.txt",
            content="Tenant runbook covers billing",
            tenant_id="tenant-a",
            kb_id="runbook",
        )
    )
    asyncio.run(upsert("chunk-stale", "stale handbook vector", namespace="kb:tenant-a:global"))
    asyncio.run(upsert("other-kb", "runbook vector", namespace="kb:tenant-a:runbook"))

    summary = reindex(ReindexRequest(owner="knowledge_base", tenant_id="tenant-a", kb_id="global"))

    global_results = asyncio.run(
        search("Tenant handbook covers Python debugging", namespace="kb:tenant-a:global")
    )
    runbook_results = asyncio.run(search("runbook vector", namespace="kb:tenant-a:runbook"))
    assert summary.scanned == 1
    assert summary.reindexed == 1
    assert summary.failed == 0
    assert [result.id for result in global_results] == [f"{document.id}:chunk:0"]
    assert "other-kb" in [result.id for result in runbook_results]
