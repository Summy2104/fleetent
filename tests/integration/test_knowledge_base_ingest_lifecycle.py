from __future__ import annotations

from dataclasses import replace

import pytest

from fleetent.config import KnowledgeBaseSettings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.knowledge_base.core import KnowledgeChunk, KnowledgeDocument, KnowledgeStore
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.parsers import ParsedDocument, ParsedSection
from fleetent.schema_migrations import migrate


async def test_delete_removes_graph_evidence_for_deleted_document(monkeypatch, tmp_path):
    database, _tracker = _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import graph_search, run_entity_extraction, runtime

    document = await _ingest_fixture_document(
        "relations.md",
        "Customer: Acme\nDepends on: Billing API -> Data Warehouse",
    )
    await run_entity_extraction("default", "global")

    mentions_before = _count(database, "SELECT COUNT(*) FROM kb_entity_mentions")
    relations_before = _count(database, "SELECT COUNT(*) FROM kb_relations")
    assert mentions_before == 1
    assert relations_before == 1

    await runtime.delete(document.id)

    mentions_after = _count(
        database,
        "SELECT COUNT(*) FROM kb_entity_mentions WHERE document_id = :document_id",
        {"document_id": document.id},
    )
    relations_after = _count(
        database,
        "SELECT COUNT(*) FROM kb_relations WHERE evidence_document_id = :document_id",
        {"document_id": document.id},
    )
    result = await graph_search("Billing API", tenant_id="default", kb_ids=["global"], depth=1)

    assert mentions_after == 0
    assert relations_after == 0
    assert result.chunks == []


async def test_delete_garbage_collects_entities_without_mentions_or_relations(
    monkeypatch, tmp_path
):
    database, _tracker = _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import run_entity_extraction, runtime

    document = await _ingest_fixture_document(
        "relations.md",
        "Depends on: Billing API -> Data Warehouse",
    )
    await run_entity_extraction("default", "global")

    entity_names_before = _entity_names(database)
    await runtime.delete(document.id)
    entity_names_after = _entity_names(database)

    assert entity_names_before == ["Billing API", "Data Warehouse"]
    assert entity_names_after == []


async def test_delete_keeps_entities_still_referenced_by_other_relations(monkeypatch, tmp_path):
    database, _tracker = _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import run_entity_extraction, runtime

    first = await _ingest_fixture_document(
        "billing-warehouse.md",
        "Depends on: Billing API -> Data Warehouse",
    )
    await _ingest_fixture_document(
        "billing-auth.md",
        "Depends on: Billing API -> Auth Service",
    )
    await run_entity_extraction("default", "global")

    await runtime.delete(first.id)

    remaining_entities = _entity_names(database)
    remaining_relations = database.execute(
        """
        SELECT evidence_document_id, relation_type
        FROM kb_relations
        ORDER BY evidence_document_id ASC
        """
    ).fetchall()

    assert remaining_entities == ["Auth Service", "Billing API"]
    assert remaining_relations == [
        {
            "evidence_document_id": remaining_relations[0]["evidence_document_id"],
            "relation_type": "depends_on",
        }
    ]


async def test_delete_is_idempotent_for_missing_document(monkeypatch, tmp_path):
    database, tracker = _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import run_entity_extraction, runtime

    document = await _ingest_fixture_document(
        "guide.md",
        "Customer: Acme\nDepends on: Billing API -> Data Warehouse",
    )
    await run_entity_extraction("default", "global")
    await runtime.delete(document.id)
    await runtime.delete(document.id)
    await runtime.delete("missing-document")

    assert _count(database, "SELECT COUNT(*) FROM knowledge_documents") == 0
    assert _count(database, "SELECT COUNT(*) FROM kb_entity_mentions") == 0
    assert _count(database, "SELECT COUNT(*) FROM kb_relations") == 0
    assert _count(database, "SELECT COUNT(*) FROM kb_entities") == 0
    assert tracker.deleted_chunk_ids == [f"{document.id}:chunk:0"]


async def test_reingest_same_identity_keeps_single_document_and_chunk_set(monkeypatch, tmp_path):
    database, tracker = _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import runtime

    first = await runtime.ingest_text(
        filename="guide.md",
        content="alpha beta gamma delta",
        tenant_id="tenant-a",
        kb_id="support",
        source="manual",
    )
    second = await runtime.ingest_text(
        filename="guide.md",
        content="replacement content only",
        tenant_id="tenant-a",
        kb_id="support",
        source="manual",
    )

    documents = database.execute(
        """
        SELECT id, filename, source
        FROM knowledge_documents
        WHERE tenant_id = :tenant_id AND kb_id = :kb_id
        ORDER BY created_at ASC, id ASC
        """,
        {"tenant_id": "tenant-a", "kb_id": "support"},
    ).fetchall()
    chunks = database.execute(
        """
        SELECT document_id, position, content
        FROM knowledge_chunks
        WHERE tenant_id = :tenant_id AND kb_id = :kb_id
        ORDER BY position ASC
        """,
        {"tenant_id": "tenant-a", "kb_id": "support"},
    ).fetchall()

    assert [row["id"] for row in documents] == [second.id]
    assert [row["content"] for row in chunks] == ["replacement content only"]
    assert tracker.deleted_chunk_ids == [f"{first.id}:chunk:0"]


async def test_reingest_replaces_old_chunks_vectors_and_graph_evidence(monkeypatch, tmp_path):
    database, tracker = _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import graph_search, run_entity_extraction, runtime

    first = await runtime.ingest_parsed(
        ParsedDocument(
            filename="runbook.md",
            format="markdown",
            sections=[
                ParsedSection(
                    title="body",
                    text="Customer: Acme\nDepends on: Billing API -> Data Warehouse",
                    level=0,
                    metadata={"path": "body"},
                )
            ],
            metadata={"filename": "runbook.md", "format": "markdown"},
        ),
        tenant_id="default",
        kb_id="global",
        source="manual",
    )
    await run_entity_extraction("default", "global")

    second = await runtime.ingest_parsed(
        ParsedDocument(
            filename="runbook.md",
            format="markdown",
            sections=[
                ParsedSection(
                    title="body",
                    text="Customer: Beta\nDepends on: Billing API -> Auth Service",
                    level=0,
                    metadata={"path": "body"},
                )
            ],
            metadata={"filename": "runbook.md", "format": "markdown"},
        ),
        tenant_id="default",
        kb_id="global",
        source="manual",
    )

    old_keyword = await runtime.search(
        "Acme",
        tenant_id="default",
        kb_ids=["global"],
        mode="keyword",
    )
    old_graph = await graph_search("Acme", tenant_id="default", kb_ids=["global"], depth=1)
    await run_entity_extraction("default", "global", document_id=second.id)
    new_keyword = await runtime.search(
        "Beta",
        tenant_id="default",
        kb_ids=["global"],
        mode="keyword",
    )
    new_graph = await graph_search("Auth Service", tenant_id="default", kb_ids=["global"], depth=1)

    assert tracker.deleted_chunk_ids == [f"{first.id}:chunk:0"]
    assert (
        _count(
            database,
            "SELECT COUNT(*) FROM kb_entity_mentions WHERE document_id = :document_id",
            {"document_id": first.id},
        )
        == 0
    )
    assert (
        _count(
            database,
            "SELECT COUNT(*) FROM kb_relations WHERE evidence_document_id = :document_id",
            {"document_id": first.id},
        )
        == 0
    )
    assert old_keyword == []
    assert old_graph.chunks == []
    assert [chunk.document_id for chunk in new_keyword] == [second.id]
    assert {chunk.chunk.document_id for chunk in new_graph.chunks} == {second.id}


async def test_reingest_same_filename_different_source_or_scope_does_not_overwrite(
    monkeypatch, tmp_path
):
    database, _tracker = _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import runtime

    manual = await runtime.ingest_text(
        filename="guide.md",
        content="manual copy",
        tenant_id="tenant-a",
        kb_id="global",
        source="manual",
    )
    connector = await runtime.ingest_text(
        filename="guide.md",
        content="connector copy",
        tenant_id="tenant-a",
        kb_id="global",
        source="google-drive",
    )
    other_scope = await runtime.ingest_text(
        filename="guide.md",
        content="other kb copy",
        tenant_id="tenant-a",
        kb_id="private",
        source="manual",
    )

    docs = database.execute(
        """
        SELECT id
        FROM knowledge_documents
        ORDER BY tenant_id ASC, kb_id ASC, source ASC, id ASC
        """
    ).fetchall()

    assert {str(row["id"]) for row in docs} == {manual.id, connector.id, other_scope.id}


async def test_reingest_collapses_existing_duplicate_identity_rows(monkeypatch, tmp_path):
    database, tracker = _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import runtime

    store = KnowledgeStore(database)
    store.ensure_knowledge_base("tenant-a", "support")
    first = KnowledgeDocument(
        id="duplicate-1",
        tenant_id="tenant-a",
        kb_id="support",
        filename="guide.md",
        source="manual",
        source_url=None,
    )
    second = replace(first, id="duplicate-2")
    store.insert_document(first)
    store.insert_document(second)
    store.insert_chunks(
        [
            KnowledgeChunk(
                id="duplicate-1:chunk:0",
                document_id="duplicate-1",
                tenant_id="tenant-a",
                kb_id="support",
                filename="guide.md",
                content="legacy duplicate one",
                position=0,
                score=0.0,
                source="manual",
                source_url=None,
            )
        ]
    )
    store.insert_chunks(
        [
            KnowledgeChunk(
                id="duplicate-2:chunk:0",
                document_id="duplicate-2",
                tenant_id="tenant-a",
                kb_id="support",
                filename="guide.md",
                content="legacy duplicate two",
                position=0,
                score=0.0,
                source="manual",
                source_url=None,
            )
        ]
    )

    document = await runtime.ingest_text(
        filename="guide.md",
        content="replacement",
        tenant_id="tenant-a",
        kb_id="support",
        source="manual",
    )

    docs = database.execute(
        """
        SELECT id
        FROM knowledge_documents
        WHERE tenant_id = :tenant_id
          AND kb_id = :kb_id
          AND filename = :filename
          AND source = :source
        ORDER BY id ASC
        """,
        {
            "tenant_id": "tenant-a",
            "kb_id": "support",
            "filename": "guide.md",
            "source": "manual",
        },
    ).fetchall()

    assert [row["id"] for row in docs] == [document.id]
    assert tracker.deleted_chunk_ids == ["duplicate-1:chunk:0", "duplicate-2:chunk:0"]


async def test_ingest_embedding_failure_leaves_no_document_chunk_fts_or_vector_residue(
    monkeypatch, tmp_path
):
    database, tracker = _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import runtime
    from fleetent.knowledge_base.ingest import runtime as ingest_runtime

    monkeypatch.setattr(runtime, "_kb_vector_backend", tracker)

    async def fail_embed_text(text: str) -> list[float]:
        raise RuntimeError(f"embedding offline for {text}")

    monkeypatch.setattr(ingest_runtime.vector_store, "embed_text", fail_embed_text)

    with pytest.raises(RuntimeError, match="embedding offline"):
        await runtime.ingest_text(
            filename="broken.md",
            content="this should never persist",
            tenant_id="tenant-a",
            kb_id="support",
            source="manual",
        )

    assert _count(database, "SELECT COUNT(*) FROM knowledge_documents") == 0
    assert _count(database, "SELECT COUNT(*) FROM knowledge_chunks") == 0
    assert _count(database, "SELECT COUNT(*) FROM knowledge_chunks_fts") == 0
    assert tracker.upsert_calls == []
    assert tracker.deleted_chunk_ids == []


async def test_reingest_embedding_failure_keeps_existing_document_searchable(monkeypatch, tmp_path):
    database, tracker = _patch_knowledge_runtime(monkeypatch, tmp_path)

    from fleetent.knowledge_base import runtime
    from fleetent.knowledge_base.ingest import runtime as ingest_runtime

    monkeypatch.setattr(runtime, "_kb_vector_backend", tracker)

    existing = await runtime.ingest_text(
        filename="guide.md",
        content="stable baseline content",
        tenant_id="tenant-a",
        kb_id="support",
        source="manual",
    )
    before_search = await runtime.search(
        "stable",
        tenant_id="tenant-a",
        kb_ids=["support"],
        mode="keyword",
    )

    async def fail_embed_text(text: str) -> list[float]:
        raise RuntimeError(f"embedding offline for {text}")

    monkeypatch.setattr(ingest_runtime.vector_store, "embed_text", fail_embed_text)

    with pytest.raises(RuntimeError, match="embedding offline"):
        await runtime.ingest_text(
            filename="guide.md",
            content="replacement that must not win",
            tenant_id="tenant-a",
            kb_id="support",
            source="manual",
        )

    documents = database.execute(
        """
        SELECT id, filename, source
        FROM knowledge_documents
        WHERE tenant_id = :tenant_id AND kb_id = :kb_id
        ORDER BY created_at ASC, id ASC
        """,
        {"tenant_id": "tenant-a", "kb_id": "support"},
    ).fetchall()
    chunks = database.execute(
        """
        SELECT document_id, position, content
        FROM knowledge_chunks
        WHERE tenant_id = :tenant_id AND kb_id = :kb_id
        ORDER BY position ASC
        """,
        {"tenant_id": "tenant-a", "kb_id": "support"},
    ).fetchall()
    after_search = await runtime.search(
        "stable",
        tenant_id="tenant-a",
        kb_ids=["support"],
        mode="keyword",
    )

    assert [row["id"] for row in documents] == [existing.id]
    assert [row["content"] for row in chunks] == ["stable baseline content"]
    assert [chunk.document_id for chunk in before_search] == [existing.id]
    assert [chunk.document_id for chunk in after_search] == [existing.id]
    assert tracker.deleted_chunk_ids == []


async def _ingest_fixture_document(filename: str, content: str):
    from fleetent.knowledge_base import runtime

    return await runtime.ingest_parsed(
        ParsedDocument(
            filename=filename,
            format="markdown",
            sections=[
                ParsedSection(title="body", text=content, level=0, metadata={"path": "body"})
            ],
            metadata={"filename": filename, "format": "markdown"},
        )
    )


def _patch_knowledge_runtime(monkeypatch, tmp_path) -> tuple[SQLiteDatabase, _VectorTracker]:
    from fleetent import vector_store as vector_store_module
    from fleetent.knowledge_base import runtime
    from fleetent.knowledge_base.ingest import runtime as ingest_runtime

    db_path = tmp_path / "knowledge.db"
    migrate(SQLiteDatabase(path=db_path), KB_MIGRATIONS)
    database = create_database(f"sqlite:///{db_path}")
    tracker = _VectorTracker()
    monkeypatch.setattr(
        runtime,
        "_kb_config",
        lambda: KnowledgeBaseSettings(chunk_size=500, chunk_overlap=0),
    )
    monkeypatch.setattr(runtime, "_database", lambda: database)
    monkeypatch.setattr(runtime, "_kb_vector_backend", None)
    monkeypatch.setattr(vector_store_module, "upsert", tracker.upsert)
    monkeypatch.setattr(vector_store_module, "delete", tracker.delete)
    monkeypatch.setattr(runtime.vector_store, "upsert", tracker.upsert)
    monkeypatch.setattr(runtime.vector_store, "delete", tracker.delete)
    monkeypatch.setattr(ingest_runtime.vector_store, "upsert", tracker.upsert)
    monkeypatch.setattr(ingest_runtime.vector_store, "delete", tracker.delete)
    return database, tracker


class _VectorTracker:
    def __init__(self) -> None:
        self.deleted_chunk_ids: list[str] = []
        self.upsert_calls: list[tuple[str, str, str]] = []

    async def upsert(self, chunk_id: str, content: str, namespace: str) -> None:
        self.upsert_calls.append((chunk_id, content, namespace))

    async def delete(self, chunk_id: str, namespace: str) -> None:
        self.deleted_chunk_ids.append(chunk_id)


def _count(database: SQLiteDatabase, sql: str, params: dict[str, object] | None = None) -> int:
    row = database.execute(sql, params or {}).fetchone()
    assert row is not None
    return int(next(iter(row.values())))


def _entity_names(database: SQLiteDatabase) -> list[str]:
    rows = database.execute("SELECT name FROM kb_entities ORDER BY name ASC").fetchall()
    return [str(row["name"]) for row in rows]
