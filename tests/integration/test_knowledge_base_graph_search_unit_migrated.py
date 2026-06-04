from fleetent.db import create_database
from fleetent.intelligence.knowledge_base.extraction import (
    ExtractedEntity,
    ExtractedRelation,
)
from fleetent.intelligence.knowledge_base.extraction_store import KnowledgeEntityStore
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk, KnowledgeDocument
from fleetent.intelligence.knowledge_base.store import KnowledgeStore
from tests.integration.test_migrations import apply_migrations


def test_match_entities_by_normalized_query_with_tenant_kb_scope(tmp_path):
    from fleetent.intelligence.knowledge_base.graph_search import match_entities

    database = _seed_entities(tmp_path)

    matches = match_entities(database, "Acme deployment", "tenant-a", ["support"])
    other_kb = match_entities(database, "Acme deployment", "tenant-a", ["sales"])
    other_tenant = match_entities(database, "Acme deployment", "tenant-b", ["support"])

    assert [(entity.entity_type, entity.name) for entity in matches] == [("customer", "Acme")]
    assert other_kb == []
    assert other_tenant == []


def test_match_entities_uses_metadata_aliases(tmp_path):
    from fleetent.intelligence.knowledge_base.graph_search import match_entities

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    store = KnowledgeEntityStore(database)
    store.upsert_entity(
        "tenant-a",
        "support",
        ExtractedEntity(
            entity_type="system",
            name="Billing API",
            metadata={"aliases": "billing service, invoice api"},
        ),
    )

    matches = match_entities(database, "invoice api dependency", "tenant-a", ["support"])

    assert [(entity.entity_type, entity.name) for entity in matches] == [("system", "Billing API")]


async def test_graph_search_depth_greater_than_one_fails_fast(monkeypatch, tmp_path):
    database = _seed_entities(tmp_path)
    _patch_graph_runtime(monkeypatch, database)

    from fleetent.intelligence.knowledge_base import graph_search

    try:
        await graph_search("Acme", "tenant-a", ["support"], depth=2)
    except ValueError as exc:
        assert "unsupported graph search depth" in str(exc)
    else:
        raise AssertionError("depth > 1 was accepted")


async def test_graph_search_limit_less_than_one_returns_empty(monkeypatch, tmp_path):
    database = _seed_entities(tmp_path)
    _patch_graph_runtime(monkeypatch, database)

    from fleetent.intelligence.knowledge_base import graph_search

    result = await graph_search("Acme", "tenant-a", ["support"], limit=0)

    assert result.chunks == []


def test_match_entities_empty_kb_ids_returns_empty(tmp_path):
    from fleetent.intelligence.knowledge_base.graph_search import match_entities

    database = _seed_entities(tmp_path)

    assert match_entities(database, "Acme", "tenant-a", []) == []


def test_match_entities_handles_list_aliases_and_bad_metadata(tmp_path):
    from fleetent.intelligence.knowledge_base.graph_search import match_entities

    db_path = tmp_path / "aliases.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    database.execute(
        """
        INSERT INTO kb_entities (
            id, tenant_id, kb_id, entity_type, name, normalized_name,
            metadata_json, created_at, updated_at
        )
        VALUES (
            'e-bad', 'tenant-a', 'support', 'system', 'Bad', 'bad',
            'not-json', '2026-01-01', '2026-01-01'
        )
        """,
        {},
    )
    database.execute(
        """
        INSERT INTO kb_entities (
            id, tenant_id, kb_id, entity_type, name, normalized_name,
            metadata_json, created_at, updated_at
        )
        VALUES (
            'e-list', 'tenant-a', 'support', 'system', 'Billing API', 'billing api',
            :metadata, '2026-01-01', '2026-01-01'
        )
        """,
        {"metadata": '{"aliases": ["invoice api", "billing svc"]}'},
    )

    matches = match_entities(database, "the invoice api is down", "tenant-a", ["support"])

    assert [entity.name for entity in matches] == ["Billing API"]


async def test_graph_search_merges_scores_for_shared_chunk(monkeypatch, tmp_path):
    database = _seed_graph(tmp_path)
    # A relation whose evidence chunk is the directly-matched Acme chunk forces
    # _add_candidate to merge a lower relation score into the higher direct score.
    entity_store = KnowledgeEntityStore(database)
    run = entity_store.insert_run(
        tenant_id="tenant-a", kb_id="support", document_id=None, extractor="merge"
    )
    acme = ExtractedEntity("customer", "Acme", metadata={"chunk_id": "doc-acme:chunk:0"})
    billing = ExtractedEntity("system", "Billing API", metadata={"chunk_id": "doc-billing:chunk:0"})
    entity_store.replace_document_evidence(
        tenant_id="tenant-a",
        kb_id="support",
        document_id="doc-acme",
        run_id=run.id,
        entities=[acme, billing],
        relations=[
            ExtractedRelation(
                relation_type="related_to",
                source=acme,
                target=billing,
                evidence_text="Acme relates to Billing.",
                chunk_id="doc-acme:chunk:0",
                document_id="doc-acme",
            )
        ],
    )
    _patch_graph_runtime(monkeypatch, database)

    from fleetent.intelligence.knowledge_base import graph_search

    result = await graph_search("tell me about Acme", "tenant-a", ["support"], depth=1)

    by_id = {item.chunk.id: item for item in result.chunks}
    # Direct match score (1.0) wins over the relation_evidence score (0.8) on merge.
    assert by_id["doc-acme:chunk:0"].graph_score == 1.0
    assert by_id["doc-acme:chunk:0"].reason == "direct_entity_match"
    assert any(
        relation.relation_type == "related_to" for relation in by_id["doc-acme:chunk:0"].relations
    )


async def test_graph_search_no_matched_entities_returns_empty(monkeypatch, tmp_path):
    database = _seed_entities(tmp_path)
    _patch_graph_runtime(monkeypatch, database)

    from fleetent.intelligence.knowledge_base import graph_search

    result = await graph_search("nothing relevant here", "tenant-a", ["support"])

    assert result.chunks == []
    assert result.tenant_id == "tenant-a"
    assert result.kb_ids == ["support"]


async def test_graph_search_depth_zero_only_direct_matches(monkeypatch, tmp_path):
    database = _seed_graph(tmp_path)
    _patch_graph_runtime(monkeypatch, database)

    from fleetent.intelligence.knowledge_base import graph_search

    result = await graph_search("tell me about Acme", "tenant-a", ["support"], depth=0)

    assert [(item.chunk.id, item.reason, item.graph_score) for item in result.chunks] == [
        ("doc-acme:chunk:0", "direct_entity_match", 1.0)
    ]
    assert [entity.name for entity in result.chunks[0].matched_entities] == ["Acme"]


async def test_graph_search_depth_one_collects_relation_and_related_evidence(monkeypatch, tmp_path):
    database = _seed_graph(tmp_path)
    _patch_graph_runtime(monkeypatch, database)

    from fleetent.intelligence.knowledge_base import graph_search

    result = await graph_search("tell me about Acme", "tenant-a", ["support"], depth=1)

    by_id = {item.chunk.id: item for item in result.chunks}
    assert by_id["doc-acme:chunk:0"].reason == "direct_entity_match"
    assert by_id["doc-acme:chunk:0"].graph_score == 1.0
    assert by_id["doc-rel:chunk:0"].reason == "relation_evidence"
    assert by_id["doc-rel:chunk:0"].graph_score == 0.8
    assert [relation.relation_type for relation in by_id["doc-rel:chunk:0"].relations] == [
        "depends_on"
    ]
    assert by_id["doc-billing:chunk:0"].reason == "related_entity_mention"
    assert by_id["doc-billing:chunk:0"].graph_score == 0.6
    assert [entity.name for entity in by_id["doc-billing:chunk:0"].matched_entities] == [
        "Billing API"
    ]


async def test_graph_search_orders_by_score_then_position_and_respects_limit(monkeypatch, tmp_path):
    database = _seed_graph(tmp_path)
    _patch_graph_runtime(monkeypatch, database)

    from fleetent.intelligence.knowledge_base import graph_search

    result = await graph_search("tell me about Acme", "tenant-a", ["support"], limit=2)

    assert [item.chunk.id for item in result.chunks] == [
        "doc-acme:chunk:0",
        "doc-rel:chunk:0",
    ]
    assert [item.graph_score for item in result.chunks] == [1.0, 0.8]


def _seed_graph(tmp_path):
    db_path = tmp_path / "graph.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")

    store = KnowledgeStore(database)
    for kb_doc, chunk_id, content in [
        ("doc-acme", "doc-acme:chunk:0", "Acme is our largest customer."),
        ("doc-rel", "doc-rel:chunk:0", "Acme depends on the Billing API."),
        ("doc-billing", "doc-billing:chunk:0", "The Billing API handles invoices."),
    ]:
        store.ensure_knowledge_base("tenant-a", "support")
        store.insert_document(
            KnowledgeDocument(
                id=kb_doc,
                tenant_id="tenant-a",
                kb_id="support",
                filename=f"{kb_doc}.md",
                source="manual",
                source_url=None,
            )
        )
        store.insert_chunks(
            [
                KnowledgeChunk(
                    id=chunk_id,
                    document_id=kb_doc,
                    tenant_id="tenant-a",
                    kb_id="support",
                    filename=f"{kb_doc}.md",
                    content=content,
                    position=0,
                    score=0.0,
                    source="manual",
                    source_url=None,
                )
            ]
        )

    entity_store = KnowledgeEntityStore(database)
    run = entity_store.insert_run(
        tenant_id="tenant-a", kb_id="support", document_id=None, extractor="test"
    )
    acme = ExtractedEntity("customer", "Acme", metadata={"chunk_id": "doc-acme:chunk:0"})
    billing = ExtractedEntity("system", "Billing API", metadata={"chunk_id": "doc-billing:chunk:0"})
    entity_store.replace_document_evidence(
        tenant_id="tenant-a",
        kb_id="support",
        document_id="doc-acme",
        run_id=run.id,
        entities=[acme],
        relations=[],
    )
    entity_store.replace_document_evidence(
        tenant_id="tenant-a",
        kb_id="support",
        document_id="doc-billing",
        run_id=run.id,
        entities=[billing],
        relations=[],
    )
    entity_store.replace_document_evidence(
        tenant_id="tenant-a",
        kb_id="support",
        document_id="doc-rel",
        run_id=run.id,
        entities=[acme, billing],
        relations=[
            ExtractedRelation(
                relation_type="depends_on",
                source=acme,
                target=billing,
                evidence_text="Acme depends on the Billing API.",
                chunk_id="doc-rel:chunk:0",
                document_id="doc-rel",
            )
        ],
    )
    return database


def _seed_entities(tmp_path):
    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    store = KnowledgeEntityStore(database)
    store.upsert_entity("tenant-a", "support", ExtractedEntity("customer", "Acme"))
    store.upsert_entity("tenant-a", "sales", ExtractedEntity("customer", "Beta"))
    store.upsert_entity("tenant-b", "support", ExtractedEntity("customer", "Gamma"))
    return database


def _patch_graph_runtime(monkeypatch, database):
    from fleetent.config import KnowledgeBaseSettings, Settings
    from fleetent.intelligence.knowledge_base import runtime

    settings = Settings(
        anthropic_api_key="test-key",
        knowledge_base=KnowledgeBaseSettings(default_tenant_id="tenant-a", default_kb_id="support"),
    )
    monkeypatch.setattr(runtime, "_database", lambda: database)
    monkeypatch.setattr(runtime, "_settings", lambda: settings)
