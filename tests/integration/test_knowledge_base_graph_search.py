from fleetent.config import KnowledgeBaseSettings
from fleetent.db import create_database
from fleetent.intelligence.knowledge_base.parsers import ParsedDocument, ParsedSection
from tests.integration.test_migrations import apply_migrations


async def test_graph_search_depth_zero_returns_direct_entity_mentions(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    acme = await _ingest("acme.md", "Customer: Acme\nProject: Atlas")
    await _ingest("beta.md", "Customer: Beta\nProject: Beacon")

    from fleetent.intelligence.knowledge_base import graph_search, run_entity_extraction

    await run_entity_extraction("default", "global")

    result = await graph_search("Acme deployment", tenant_id="default", kb_ids=["global"], depth=0)

    assert result.query == "Acme deployment"
    assert result.depth == 0
    assert [chunk.chunk.document_id for chunk in result.chunks] == [acme.id]
    assert result.chunks[0].graph_score == 1.0
    assert result.chunks[0].reason == "direct_entity_match"
    assert [entity.name for entity in result.chunks[0].matched_entities] == ["Acme"]
    assert result.chunks[0].evidence_chunk_ids == [f"{acme.id}:chunk:0"]


async def test_graph_search_depth_one_expands_relation_evidence_and_related_mentions(
    monkeypatch,
    tmp_path,
):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    billing = await _ingest("billing.md", "System: Billing API")
    warehouse = await _ingest("warehouse.md", "System: Data Warehouse")
    relation = await _ingest("relation.md", "Depends on: Billing API -> Data Warehouse")

    from fleetent.intelligence.knowledge_base import graph_search, run_entity_extraction

    await run_entity_extraction("default", "global")

    result = await graph_search("Billing API dependency", "default", ["global"], depth=1)

    chunks_by_doc = {chunk.chunk.document_id: chunk for chunk in result.chunks}
    assert set(chunks_by_doc) == {billing.id, warehouse.id, relation.id}
    assert chunks_by_doc[billing.id].reason == "direct_entity_match"
    assert chunks_by_doc[relation.id].reason == "relation_evidence"
    assert chunks_by_doc[warehouse.id].reason == "related_entity_mention"


async def test_graph_search_directional_relations_do_not_reverse_expand(monkeypatch, tmp_path):
    _patch_knowledge_runtime(monkeypatch, tmp_path)
    billing = await _ingest("billing.md", "System: Billing API")
    warehouse = await _ingest("warehouse.md", "System: Data Warehouse")
    await _ingest("relation.md", "Depends on: Billing API -> Data Warehouse")

    from fleetent.intelligence.knowledge_base import graph_search, run_entity_extraction

    await run_entity_extraction("default", "global")

    result = await graph_search("Data Warehouse", "default", ["global"], depth=1)

    assert billing.id not in {chunk.chunk.document_id for chunk in result.chunks}
    assert warehouse.id in {chunk.chunk.document_id for chunk in result.chunks}


async def _ingest(filename: str, content: str):
    from fleetent.intelligence.knowledge_base import runtime

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


def _patch_knowledge_runtime(monkeypatch, tmp_path):
    from fleetent.intelligence.knowledge_base import runtime

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    config = KnowledgeBaseSettings(chunk_size=500, chunk_overlap=0)
    monkeypatch.setattr(runtime, "_database", lambda: database)
    monkeypatch.setattr(runtime, "_kb_config", lambda: config)
    monkeypatch.setattr(runtime.vector_store, "upsert", _noop_upsert)
    monkeypatch.setattr(runtime.vector_store, "delete", _noop_delete)
    return database


async def _noop_upsert(chunk_id: str, content: str, namespace: str) -> None:
    return None


async def _noop_delete(chunk_id: str, namespace: str) -> None:
    return None
