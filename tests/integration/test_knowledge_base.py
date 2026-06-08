import pytest

from fleetent.config import KnowledgeBaseSettings
from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


def _patch_runtime_database(monkeypatch, tmp_path):
    from fleetent.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(runtime, "_database", lambda: database)
    return database


def _patch_runtime_settings(monkeypatch, **knowledge_base):
    from fleetent.knowledge_base import runtime

    config = KnowledgeBaseSettings(**knowledge_base)
    monkeypatch.setattr(runtime, "_kb_config", lambda: config)
    return config


async def test_ingest_text_creates_document_and_deterministic_chunks(monkeypatch, tmp_path):
    database = _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=8, chunk_overlap=2)

    from fleetent.knowledge_base import runtime

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

    from fleetent.knowledge_base import runtime

    with pytest.raises(ValueError, match="content must not be empty"):
        await runtime.ingest_text(filename="empty.md", content=content)


async def test_ingest_text_indexes_each_chunk_in_vector_store(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=5, chunk_overlap=1)

    from fleetent.knowledge_base import runtime

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


async def test_ingest_parsed_creates_chunks_from_sections(monkeypatch, tmp_path):
    database = _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=100, chunk_overlap=0)

    from fleetent.knowledge_base import ParsedDocument, ParsedSection, runtime

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    parsed = ParsedDocument(
        filename="guide.md",
        format="markdown",
        sections=[
            ParsedSection(
                title="Intro",
                text="Welcome",
                level=1,
                metadata={"path": "Intro"},
            ),
            ParsedSection(
                title="Install",
                text="Run setup",
                level=2,
                metadata={"path": "Intro > Install"},
            ),
        ],
        metadata={"filename": "guide.md", "format": "markdown"},
    )

    document = await runtime.ingest_parsed(
        parsed,
        tenant_id="tenant-a",
        kb_id="global",
        source="manual",
        source_url="https://example.test/guide",
    )

    chunk_rows = database.execute(
        """
        SELECT position, content
        FROM knowledge_chunks
        WHERE document_id = :document_id
        ORDER BY position ASC
        """,
        {"document_id": document.id},
    ).fetchall()

    assert [row["content"] for row in chunk_rows] == ["Welcome", "Run setup"]
    assert [row["position"] for row in chunk_rows] == [0, 1]


async def test_ingest_parsed_preserves_section_metadata_on_chunks(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=100, chunk_overlap=0)

    from fleetent.knowledge_base import ParsedDocument, ParsedSection, runtime
    from fleetent.vector_store import SearchResult

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    parsed = ParsedDocument(
        filename="guide.md",
        format="markdown",
        sections=[
            ParsedSection(
                title="Install",
                text="Run setup",
                level=2,
                metadata={"path": "Intro > Install"},
            )
        ],
        metadata={"filename": "guide.md", "format": "markdown"},
    )
    document = await runtime.ingest_parsed(parsed, tenant_id="tenant-a", kb_id="global")

    async def vector_search(query: str, namespace: str, limit: int):
        return [SearchResult(id=f"{document.id}:chunk:0", score=0.9)]

    monkeypatch.setattr(runtime.vector_store, "search", vector_search)

    results = await runtime.search("setup", tenant_id="tenant-a", kb_ids=["global"])

    assert results[0].metadata == {
        "document_format": "markdown",
        "section_level": "2",
        "section_path": "Intro > Install",
        "section_title": "Install",
    }


async def test_ingest_text_indexes_each_chunk_for_keyword_search(monkeypatch, tmp_path):
    database = _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=40, chunk_overlap=0)

    from fleetent.knowledge_base import runtime

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)

    document = await runtime.ingest_text(
        filename="ops.txt",
        content="Restart service when ERR42 appears.",
        tenant_id="tenant-a",
        kb_id="support",
    )

    rows = database.execute(
        """
        SELECT chunk_id, tenant_id, kb_id, content
        FROM knowledge_chunks_fts
        WHERE knowledge_chunks_fts MATCH :query
        """,
        {"query": "ERR42"},
    ).fetchall()

    assert rows == [
        {
            "chunk_id": f"{document.id}:chunk:0",
            "tenant_id": "tenant-a",
            "kb_id": "support",
            "content": "Restart service when ERR42 appears.",
        }
    ]


async def test_search_queries_vector_store_by_knowledge_namespace(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=20, chunk_overlap=0)

    from fleetent.knowledge_base import runtime
    from fleetent.vector_store import SearchResult

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

    from fleetent.knowledge_base import runtime
    from fleetent.vector_store import SearchResult

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

    from fleetent.knowledge_base import runtime
    from fleetent.vector_store import SearchResult

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


async def test_keyword_search_finds_exact_product_ids_and_error_codes(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=120, chunk_overlap=0)

    from fleetent.knowledge_base import runtime

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    document = await runtime.ingest_text(
        filename="runbook.md",
        content="Product FT-9000 reports ERR-42 when the pressure valve is locked.",
        tenant_id="tenant-a",
        kb_id="support",
    )

    results = await runtime.search(
        "FT-9000 ERR-42",
        tenant_id="tenant-a",
        kb_ids=["support"],
        limit=5,
        mode="keyword",
    )

    assert [(chunk.id, chunk.content) for chunk in results] == [
        (
            f"{document.id}:chunk:0",
            "Product FT-9000 reports ERR-42 when the pressure valve is locked.",
        )
    ]


async def test_keyword_search_filters_by_tenant_and_kb(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=120, chunk_overlap=0)

    from fleetent.knowledge_base import runtime

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    tenant_a_global = await runtime.ingest_text(
        filename="a-global.md",
        content="Shared incident keyword ALPHA-777 belongs to tenant a global.",
        tenant_id="tenant-a",
        kb_id="global",
    )
    await runtime.ingest_text(
        filename="a-private.md",
        content="Shared incident keyword ALPHA-777 belongs to tenant a private.",
        tenant_id="tenant-a",
        kb_id="private",
    )
    await runtime.ingest_text(
        filename="b-global.md",
        content="Shared incident keyword ALPHA-777 belongs to tenant b global.",
        tenant_id="tenant-b",
        kb_id="global",
    )

    results = await runtime.search(
        "ALPHA-777",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=10,
        mode="keyword",
    )

    assert [chunk.document_id for chunk in results] == [tenant_a_global.id]
    assert [chunk.tenant_id for chunk in results] == ["tenant-a"]
    assert [chunk.kb_id for chunk in results] == ["global"]


async def test_keyword_search_respects_limit_and_stable_ordering(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=30, chunk_overlap=0)

    from fleetent.knowledge_base import runtime

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    document = await runtime.ingest_text(
        filename="ordered.md",
        content="MATCH first sentence. MATCH second sentence. MATCH third sentence.",
        tenant_id="tenant-a",
        kb_id="global",
    )

    results = await runtime.search(
        "MATCH",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=2,
        mode="keyword",
    )

    assert [(chunk.id, chunk.position) for chunk in results] == [
        (f"{document.id}:chunk:0", 0),
        (f"{document.id}:chunk:1", 1),
    ]


async def test_hybrid_search_merges_vector_and_keyword_candidates(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=120, chunk_overlap=0)

    from fleetent.knowledge_base import runtime
    from fleetent.vector_store import SearchResult

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    vector_doc = await runtime.ingest_text(
        filename="semantic.md",
        content="Semantic troubleshooting guide for restart failures.",
        tenant_id="tenant-a",
        kb_id="global",
    )
    keyword_doc = await runtime.ingest_text(
        filename="keyword.md",
        content="Exact error code ZX-404 requires a firmware reset.",
        tenant_id="tenant-a",
        kb_id="global",
    )

    async def vector_search(query: str, namespace: str, limit: int):
        return [SearchResult(id=f"{vector_doc.id}:chunk:0", score=0.7)]

    monkeypatch.setattr(runtime.vector_store, "search", vector_search)

    results = await runtime.search(
        "ZX-404",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=5,
        mode="hybrid",
    )

    assert {chunk.id for chunk in results} == {
        f"{vector_doc.id}:chunk:0",
        f"{keyword_doc.id}:chunk:0",
    }


async def test_hybrid_search_deduplicates_and_boosts_dual_matches(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=120, chunk_overlap=0)

    from fleetent.knowledge_base import runtime
    from fleetent.vector_store import SearchResult

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    vector_only_doc = await runtime.ingest_text(
        filename="vector-only.md",
        content="General semantic guide for service failures.",
        tenant_id="tenant-a",
        kb_id="global",
    )
    dual_doc = await runtime.ingest_text(
        filename="dual.md",
        content="Service failure ERROR500 has exact recovery steps.",
        tenant_id="tenant-a",
        kb_id="global",
    )

    async def vector_search(query: str, namespace: str, limit: int):
        return [
            SearchResult(id=f"{vector_only_doc.id}:chunk:0", score=0.99),
            SearchResult(id=f"{dual_doc.id}:chunk:0", score=0.2),
        ]

    monkeypatch.setattr(runtime.vector_store, "search", vector_search)

    results = await runtime.search(
        "ERROR500",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=5,
        mode="hybrid",
    )

    assert [chunk.id for chunk in results] == [
        f"{dual_doc.id}:chunk:0",
        f"{vector_only_doc.id}:chunk:0",
    ]


async def test_hybrid_search_degrades_when_one_side_is_empty(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=120, chunk_overlap=0)

    from fleetent.knowledge_base import runtime
    from fleetent.vector_store import SearchResult

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    keyword_doc = await runtime.ingest_text(
        filename="keyword-only.md",
        content="Keyword-only code KWD123 appears in this chunk.",
        tenant_id="tenant-a",
        kb_id="global",
    )
    vector_doc = await runtime.ingest_text(
        filename="vector-only.md",
        content="Semantic-only content is available through vector search.",
        tenant_id="tenant-a",
        kb_id="global",
    )

    async def vector_empty(query: str, namespace: str, limit: int):
        return []

    monkeypatch.setattr(runtime.vector_store, "search", vector_empty)
    keyword_results = await runtime.search(
        "KWD123",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=5,
        mode="hybrid",
    )

    async def vector_only(query: str, namespace: str, limit: int):
        return [SearchResult(id=f"{vector_doc.id}:chunk:0", score=0.8)]

    monkeypatch.setattr(runtime.vector_store, "search", vector_only)
    vector_results = await runtime.search(
        "no-keyword-hit",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=5,
        mode="hybrid",
    )

    assert [chunk.id for chunk in keyword_results] == [f"{keyword_doc.id}:chunk:0"]
    assert [chunk.id for chunk in vector_results] == [f"{vector_doc.id}:chunk:0"]


async def test_hybrid_rerank_uses_public_provider_results_to_reorder(monkeypatch, tmp_path):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=120, chunk_overlap=0)

    from fleetent.config import RerankSettings, Settings
    from fleetent.knowledge_base import runtime
    from fleetent.vector_store import RerankResult, SearchResult

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    distractor_doc = await runtime.ingest_text(
        filename="distractor.md",
        content="ZX-777 generic restart notes for routine incidents.",
        tenant_id="tenant-a",
        kb_id="global",
    )
    expected_doc = await runtime.ingest_text(
        filename="answer.md",
        content="ZX-777 exact remediation requires clearing the edge cache.",
        tenant_id="tenant-a",
        kb_id="global",
    )
    calls: list[tuple[list[str], int | None]] = []

    class FakeReranker:
        async def rerank(
            self, query: str, documents: list[str], top_n: int | None = None
        ) -> list[RerankResult]:
            calls.append((documents, top_n))
            return [RerankResult(index=1, score=0.98), RerankResult(index=0, score=0.10)]

    async def vector_search(query: str, namespace: str, limit: int):
        assert limit == runtime._rerank_candidate_limit(2)
        return [
            SearchResult(id=f"{distractor_doc.id}:chunk:0", score=0.95),
            SearchResult(id=f"{expected_doc.id}:chunk:0", score=0.70),
        ]

    settings = Settings(rerank=RerankSettings(backend="disabled"))
    monkeypatch.setattr(runtime, "_settings", lambda: settings)
    monkeypatch.setattr(runtime.vector_store, "search", vector_search)
    monkeypatch.setattr(
        runtime.rerank_runtime,
        "create_rerank_provider",
        lambda rerank_settings: FakeReranker(),
    )

    results = await runtime.search(
        "ZX-777",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=2,
        mode="hybrid",
        rerank=True,
    )

    assert [chunk.id for chunk in results] == [
        f"{expected_doc.id}:chunk:0",
        f"{distractor_doc.id}:chunk:0",
    ]
    assert results[0].score == 0.98
    assert calls == [
        (
            [
                "ZX-777 generic restart notes for routine incidents.",
                "ZX-777 exact remediation requires clearing the edge cache.",
            ],
            2,
        )
    ]


async def test_hybrid_rerank_provider_failure_returns_original_hybrid_order(
    monkeypatch,
    tmp_path,
):
    _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=120, chunk_overlap=0)

    from fleetent.config import Settings
    from fleetent.knowledge_base import runtime
    from fleetent.vector_store import SearchResult
    from fleetent.vector_store.rerank import RerankProviderError

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    first_doc = await runtime.ingest_text(
        filename="first.md",
        content="ZX-888 primary recovery instructions.",
        tenant_id="tenant-a",
        kb_id="global",
    )
    second_doc = await runtime.ingest_text(
        filename="second.md",
        content="ZX-888 secondary recovery instructions.",
        tenant_id="tenant-a",
        kb_id="global",
    )

    class FailingReranker:
        async def rerank(
            self, query: str, documents: list[str], top_n: int | None = None
        ) -> list[object]:
            raise RerankProviderError("provider unavailable")

    async def vector_search(query: str, namespace: str, limit: int):
        return [
            SearchResult(id=f"{first_doc.id}:chunk:0", score=0.95),
            SearchResult(id=f"{second_doc.id}:chunk:0", score=0.70),
        ]

    monkeypatch.setattr(runtime, "_settings", lambda: Settings())
    monkeypatch.setattr(runtime.vector_store, "search", vector_search)
    baseline = await runtime.search(
        "ZX-888",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=2,
        mode="hybrid",
    )
    monkeypatch.setattr(
        runtime.rerank_runtime,
        "create_rerank_provider",
        lambda rerank_settings: FailingReranker(),
    )

    results = await runtime.search(
        "ZX-888",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=2,
        mode="hybrid",
        rerank=True,
    )

    assert [chunk.id for chunk in results] == [chunk.id for chunk in baseline]


async def test_delete_removes_document_chunks_and_vector_entries(monkeypatch, tmp_path):
    database = _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=5, chunk_overlap=1)

    from fleetent.knowledge_base import runtime

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


async def test_delete_removes_keyword_index_entries(monkeypatch, tmp_path):
    database = _patch_runtime_database(monkeypatch, tmp_path)
    _patch_runtime_settings(monkeypatch, chunk_size=40, chunk_overlap=0)

    from fleetent.knowledge_base import runtime

    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    monkeypatch.setattr(runtime.vector_store, "delete", _noop_delete)
    document = await runtime.ingest_text(
        filename="delete-keyword.md",
        content="Delete searchable ERR99 from keyword index.",
        tenant_id="tenant-a",
        kb_id="global",
    )

    await runtime.delete(document.id)

    rows = database.execute(
        """
        SELECT chunk_id
        FROM knowledge_chunks_fts
        WHERE knowledge_chunks_fts MATCH :query
        """,
        {"query": "ERR99"},
    ).fetchall()

    assert rows == []


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None


async def _noop_delete(chunk_id: str, namespace: str) -> None:
    return None
