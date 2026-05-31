import pytest

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


def _patch_runtime_database(monkeypatch, tmp_path):
    from fleetent.intelligence.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(runtime, "_database", lambda: database)
    return database


def _patch_runtime_settings(monkeypatch, **knowledge_base):
    from fleetent.intelligence.knowledge_base import runtime

    settings = Settings(
        anthropic_api_key="test-key",
        knowledge_base=KnowledgeBaseSettings(**knowledge_base),
    )
    monkeypatch.setattr(runtime, "_settings", lambda: settings)
    return settings


async def test_ingest_text_creates_document_and_deterministic_chunks(monkeypatch, tmp_path):
    database = _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=8, chunk_overlap=2)

    from fleetent.intelligence.knowledge_base import runtime

    async def upsert(chunk_id: str, content: str, namespace: str) -> None:
        return None

    monkeypatch.setattr(runtime.vector_store, "upsert", upsert)

    document = await runtime.ingest_text(
        filename="notes.md",
        content="abcdefghijklmnopqrst",
        tenant_id="tenant-a",
        kb_id="handbook",
        source="manual",
        source_url="https://example.test/notes",
    )

    document_row = database.execute(
        """
        SELECT id, tenant_id, kb_id, filename, source, source_url
        FROM knowledge_documents
        WHERE id = :id
        """,
        {"id": document.id},
    ).fetchone()
    chunk_rows = database.execute(
        """
        SELECT document_id, tenant_id, kb_id, position, content
        FROM knowledge_chunks
        WHERE document_id = :document_id
        ORDER BY position ASC
        """,
        {"document_id": document.id},
    ).fetchall()

    assert document_row == {
        "id": document.id,
        "tenant_id": "tenant-a",
        "kb_id": "handbook",
        "filename": "notes.md",
        "source": "manual",
        "source_url": "https://example.test/notes",
    }
    assert [row["content"] for row in chunk_rows] == [
        "abcdefgh",
        "ghijklmn",
        "mnopqrst",
    ]
    assert [row["position"] for row in chunk_rows] == [0, 1, 2]


@pytest.mark.parametrize("content", ["", "   \n\t  "])
async def test_ingest_text_rejects_empty_content(monkeypatch, tmp_path, content):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch)

    from fleetent.intelligence.knowledge_base import runtime

    with pytest.raises(ValueError, match="content must not be empty"):
        await runtime.ingest_text(filename="empty.md", content=content)


async def test_ingest_text_indexes_each_chunk_in_vector_store(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=5, chunk_overlap=1)

    from fleetent.intelligence.knowledge_base import runtime

    upserts: list[tuple[str, str, str]] = []

    async def upsert(chunk_id: str, content: str, namespace: str) -> None:
        upserts.append((chunk_id, content, namespace))

    monkeypatch.setattr(runtime.vector_store, "upsert", upsert)

    document = await runtime.ingest_text(
        filename="guide.txt",
        content="abcdefghijkl",
        tenant_id="tenant-a",
        kb_id="global",
    )

    assert upserts == [
        (f"{document.id}:chunk:0", "abcde", "kb:tenant-a:global"),
        (f"{document.id}:chunk:1", "efghi", "kb:tenant-a:global"),
        (f"{document.id}:chunk:2", "ijkl", "kb:tenant-a:global"),
    ]


async def test_search_queries_vector_store_by_knowledge_namespace(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=20, chunk_overlap=0)

    from fleetent.intelligence.knowledge_base import runtime
    from fleetent.intelligence.vector_store import SearchResult

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    document = await runtime.ingest_text(
        filename="guide.txt",
        content="tenant handbook",
        tenant_id="tenant-a",
        kb_id="global",
    )
    calls: list[tuple[str, str, int]] = []

    async def vector_search(query: str, namespace: str, limit: int):
        calls.append((query, namespace, limit))
        return [SearchResult(id=f"{document.id}:chunk:0", score=0.75)]

    monkeypatch.setattr(runtime.vector_store, "search", vector_search)

    results = await runtime.search("handbook", tenant_id="tenant-a", kb_ids=["global"], limit=3)

    assert calls == [("handbook", "kb:tenant-a:global", 3)]
    assert [(chunk.id, chunk.filename, chunk.content, chunk.score) for chunk in results] == [
        (f"{document.id}:chunk:0", "guide.txt", "tenant handbook", 0.75)
    ]


async def test_search_merges_multiple_kbs_with_stable_ordering(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=6, chunk_overlap=0)

    from fleetent.intelligence.knowledge_base import runtime
    from fleetent.intelligence.vector_store import SearchResult

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    global_doc = await runtime.ingest_text(
        filename="global.txt",
        content="aaaabbbbcccc",
        tenant_id="tenant-a",
        kb_id="global",
    )
    team_doc = await runtime.ingest_text(
        filename="team.txt",
        content="ddddeeeeffff",
        tenant_id="tenant-a",
        kb_id="team",
    )

    async def vector_search(query: str, namespace: str, limit: int):
        if namespace == "kb:tenant-a:global":
            return [
                SearchResult(id=f"{global_doc.id}:chunk:1", score=0.9),
                SearchResult(id=f"{global_doc.id}:chunk:0", score=0.9),
            ]
        if namespace == "kb:tenant-a:team":
            return [SearchResult(id=f"{team_doc.id}:chunk:0", score=0.95)]
        return []

    monkeypatch.setattr(runtime.vector_store, "search", vector_search)

    results = await runtime.search(
        "query", tenant_id="tenant-a", kb_ids=["global", "team"], limit=3
    )

    assert [(chunk.id, chunk.score, chunk.position) for chunk in results] == [
        (f"{team_doc.id}:chunk:0", 0.95, 0),
        (f"{global_doc.id}:chunk:0", 0.9, 0),
        (f"{global_doc.id}:chunk:1", 0.9, 1),
    ]


async def test_search_is_tenant_isolated(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=20, chunk_overlap=0)

    from fleetent.intelligence.knowledge_base import runtime
    from fleetent.intelligence.vector_store import SearchResult

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    tenant_a_doc = await runtime.ingest_text(
        filename="a.txt",
        content="shared topic for tenant a",
        tenant_id="tenant-a",
        kb_id="global",
    )
    tenant_b_doc = await runtime.ingest_text(
        filename="b.txt",
        content="shared topic for tenant b",
        tenant_id="tenant-b",
        kb_id="global",
    )

    async def vector_search(query: str, namespace: str, limit: int):
        assert namespace == "kb:tenant-a:global"
        return [
            SearchResult(id=f"{tenant_a_doc.id}:chunk:0", score=0.8),
            SearchResult(id=f"{tenant_b_doc.id}:chunk:0", score=0.99),
        ]

    monkeypatch.setattr(runtime.vector_store, "search", vector_search)

    results = await runtime.search("shared", tenant_id="tenant-a", kb_ids=["global"], limit=10)

    assert [chunk.tenant_id for chunk in results] == ["tenant-a"]
    assert [chunk.document_id for chunk in results] == [tenant_a_doc.id]


async def test_delete_removes_document_chunks_and_vector_entries(monkeypatch, tmp_path):
    database = _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=5, chunk_overlap=1)

    from fleetent.intelligence.knowledge_base import runtime

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    vector_deletes: list[tuple[str, str]] = []

    async def vector_delete(chunk_id: str, namespace: str) -> None:
        vector_deletes.append((chunk_id, namespace))

    monkeypatch.setattr(runtime.vector_store, "delete", vector_delete)
    document = await runtime.ingest_text(
        filename="delete.md",
        content="abcdefghijkl",
        tenant_id="tenant-a",
        kb_id="global",
    )

    await runtime.delete(document.id)
    await runtime.delete(document.id)

    remaining_documents = database.execute(
        "SELECT id FROM knowledge_documents WHERE id = :id",
        {"id": document.id},
    ).fetchall()
    remaining_chunks = database.execute(
        "SELECT id FROM knowledge_chunks WHERE document_id = :document_id",
        {"document_id": document.id},
    ).fetchall()

    assert remaining_documents == []
    assert remaining_chunks == []
    assert vector_deletes == [
        (f"{document.id}:chunk:0", "kb:tenant-a:global"),
        (f"{document.id}:chunk:1", "kb:tenant-a:global"),
        (f"{document.id}:chunk:2", "kb:tenant-a:global"),
    ]


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None
