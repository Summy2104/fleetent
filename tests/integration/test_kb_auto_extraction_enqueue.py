from __future__ import annotations

import sqlite3
from pathlib import Path

from fleetent.db import SQLiteDatabase, create_database
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.schema_migrations import migrate


def _prepare_local_queue(tmp_path: Path) -> tuple[Path, str]:
    queue_path = tmp_path / "kb-ingest-queue.db"
    queue_url = f"sqlite:///{queue_path}"
    from fleetent import kb_ingest_jobs

    kb_ingest_jobs.get_job("missing", database_url=queue_url)
    return queue_path, queue_url


def _patch_runtime_database(monkeypatch, tmp_path: Path, *, queue_url: str):
    from fleetent.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    migrate(SQLiteDatabase(path=db_path), KB_MIGRATIONS)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(runtime, "_database", lambda: database)
    monkeypatch.setattr(runtime, "_kb_queue_database_url", queue_url)
    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    monkeypatch.setattr(runtime.vector_store, "delete", _noop_delete)
    return database


def _job_rows(management_db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(management_db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT id, job_type, tenant_id, kb_id, connector_ref
            FROM kb_ingest_jobs
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
    finally:
        conn.close()


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None


async def _noop_delete(chunk_id: str, namespace: str) -> None:
    return None


async def test_enabled_kb_ingest_enqueues_extraction_job(monkeypatch, tmp_path) -> None:
    queue_db_path, queue_url = _prepare_local_queue(tmp_path)
    _patch_runtime_database(monkeypatch, tmp_path, queue_url=queue_url)

    from fleetent import kb_ingest_jobs
    from fleetent.knowledge_base import runtime

    runtime.create_knowledge_base(
        "tenant-a",
        "support",
        "Support handbook",
        extraction_enabled=True,
    )

    document = await runtime.ingest_text(
        filename="guide.md",
        content="hello world",
        tenant_id="tenant-a",
        kb_id="support",
        source="manual",
    )

    rows = _job_rows(queue_db_path)

    assert document.id
    assert len(rows) == 1
    assert rows[0]["job_type"] == "extraction"
    assert kb_ingest_jobs.get_job_payload(dict(rows[0]))["document_id"] == document.id


async def test_disabled_kb_ingest_does_not_enqueue_extraction_job(monkeypatch, tmp_path) -> None:
    queue_db_path, queue_url = _prepare_local_queue(tmp_path)
    _patch_runtime_database(monkeypatch, tmp_path, queue_url=queue_url)

    from fleetent.knowledge_base import runtime

    runtime.create_knowledge_base("tenant-a", "support", "Support handbook")

    await runtime.ingest_text(
        filename="guide.md",
        content="hello world",
        tenant_id="tenant-a",
        kb_id="support",
        source="manual",
    )

    assert _job_rows(queue_db_path) == []


async def test_reingest_overwrite_enqueues_extraction_for_new_document(
    monkeypatch, tmp_path
) -> None:
    queue_db_path, queue_url = _prepare_local_queue(tmp_path)
    database = _patch_runtime_database(monkeypatch, tmp_path, queue_url=queue_url)

    from fleetent import kb_ingest_jobs
    from fleetent.knowledge_base import runtime

    runtime.create_knowledge_base(
        "tenant-a",
        "support",
        "Support handbook",
        extraction_enabled=True,
    )

    first = await runtime.ingest_text(
        filename="guide.md",
        content="alpha",
        tenant_id="tenant-a",
        kb_id="support",
        source="manual",
    )
    second = await runtime.ingest_text(
        filename="guide.md",
        content="beta",
        tenant_id="tenant-a",
        kb_id="support",
        source="manual",
    )

    rows = _job_rows(queue_db_path)
    active_documents = database.execute(
        """
        SELECT id
        FROM knowledge_documents
        WHERE tenant_id = :tenant_id AND kb_id = :kb_id
        ORDER BY created_at ASC, id ASC
        """,
        {"tenant_id": "tenant-a", "kb_id": "support"},
    ).fetchall()

    assert [row["id"] for row in active_documents] == [second.id]
    assert len(rows) == 2
    assert [kb_ingest_jobs.get_job_payload(dict(row))["document_id"] for row in rows] == [
        first.id,
        second.id,
    ]
