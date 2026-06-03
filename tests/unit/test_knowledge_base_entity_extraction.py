import pytest


def test_extraction_models_validate_supported_entity_and_relation_types():
    from fleetent.intelligence.knowledge_base.extraction import (
        ExtractedEntity,
        ExtractedRelation,
        validate_entity_type,
        validate_relation_type,
    )

    assert validate_entity_type("customer") == "customer"
    assert validate_relation_type("depends_on") == "depends_on"
    assert ExtractedEntity(entity_type="project", name="Atlas").normalized_name == "atlas"
    relation = ExtractedRelation(
        relation_type="depends_on",
        source=ExtractedEntity(entity_type="system", name="Billing API"),
        target=ExtractedEntity(entity_type="system", name="Data Warehouse"),
        evidence_text="Billing API depends on Data Warehouse",
        chunk_id="chunk-1",
        document_id="doc-1",
    )

    assert relation.relation_type == "depends_on"


@pytest.mark.parametrize("entity_type", ["vendor", "feature", ""])
def test_unsupported_entity_type_fails_fast(entity_type):
    from fleetent.intelligence.knowledge_base.extraction import ExtractedEntity

    with pytest.raises(ValueError, match="unsupported entity type"):
        ExtractedEntity(entity_type=entity_type, name="Acme")


@pytest.mark.parametrize("relation_type", ["serves", "blocks", ""])
def test_unsupported_relation_type_fails_fast(relation_type):
    from fleetent.intelligence.knowledge_base.extraction import (
        ExtractedEntity,
        ExtractedRelation,
    )

    with pytest.raises(ValueError, match="unsupported relation type"):
        ExtractedRelation(
            relation_type=relation_type,
            source=ExtractedEntity(entity_type="system", name="Billing API"),
            target=ExtractedEntity(entity_type="system", name="Data Warehouse"),
            evidence_text="evidence",
            chunk_id="chunk-1",
            document_id="doc-1",
        )


def test_entity_name_normalization_trims_casefolds_and_collapses_whitespace():
    from fleetent.intelligence.knowledge_base.extraction import normalize_entity_name

    assert normalize_entity_name("  Customer   A\nTeam ") == "customer a team"


def test_entity_store_upsert_merges_within_kb_and_keeps_kbs_separate(tmp_path):
    from fleetent.db import create_database
    from fleetent.intelligence.knowledge_base.extraction import ExtractedEntity
    from fleetent.intelligence.knowledge_base.extraction_store import KnowledgeEntityStore
    from tests.integration.test_migrations import apply_migrations

    db_path = tmp_path / "knowledge.db"
    apply_migrations(db_path)
    store = KnowledgeEntityStore(create_database(f"sqlite:///{db_path}"))

    first = store.upsert_entity("tenant-a", "support", ExtractedEntity("customer", "Customer A"))
    second = store.upsert_entity("tenant-a", "support", ExtractedEntity("customer", " customer a "))
    other_kb = store.upsert_entity("tenant-a", "sales", ExtractedEntity("customer", "Customer A"))

    assert first.id == second.id
    assert first.id != other_kb.id
    assert first.normalized_name == "customer a"
    assert other_kb.kb_id == "sales"


def test_deterministic_extractor_extracts_fixture_entities():
    from fleetent.intelligence.knowledge_base.extraction import deterministic_extract

    result = deterministic_extract(
        """
        Customer: Acme
        Project: Atlas
        System: Billing API
        Team: Platform
        Concept: Revenue Operations
        Term: ARR
        """,
        document_id="doc-1",
        chunk_id="chunk-1",
    )

    assert {(entity.entity_type, entity.name) for entity in result.entities} == {
        ("customer", "Acme"),
        ("project", "Atlas"),
        ("system", "Billing API"),
        ("team", "Platform"),
        ("concept", "Revenue Operations"),
        ("term", "ARR"),
    }


def test_deterministic_extractor_extracts_relations_with_chunk_evidence():
    from fleetent.intelligence.knowledge_base.extraction import deterministic_extract

    result = deterministic_extract(
        """
        System: Billing API
        System: Data Warehouse
        Depends on: Billing API -> Data Warehouse
        Defines: ARR -> Annual recurring revenue
        Conflict: Legacy Billing conflicts with Billing API
        """,
        document_id="doc-1",
        chunk_id="chunk-1",
    )

    assert [
        (relation.relation_type, relation.source.name, relation.target.name)
        for relation in result.relations
    ] == [
        ("depends_on", "Billing API", "Data Warehouse"),
        ("defines", "ARR", "Annual recurring revenue"),
        ("conflicts_with", "Legacy Billing", "Billing API"),
    ]
    assert {relation.chunk_id for relation in result.relations} == {"chunk-1"}
    assert {relation.document_id for relation in result.relations} == {"doc-1"}
