from fleetent.db import create_database
from fleetent.intelligence.knowledge_base.extraction import ExtractedEntity
from fleetent.intelligence.knowledge_base.extraction_store import KnowledgeEntityStore
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
