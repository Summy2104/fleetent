"""Pure deterministic KB extraction: entity/relation parsing + validators."""

import pytest

from fleetent.intelligence.knowledge_base.extraction import (
    ExtractedEntity,
    ExtractedRelation,
    deterministic_extract,
    normalize_entity_name,
    validate_entity_type,
    validate_relation_type,
)


def _extract(text: str):
    return deterministic_extract(text, document_id="doc1", chunk_id="chunk1")


def test_entity_labels_become_entities():
    result = _extract("Person: Alice\nTeam: Platform\nConcept: Caching")
    by_name = {e.name: e for e in result.entities}
    assert by_name["Alice"].entity_type == "person"
    assert by_name["Platform"].entity_type == "team"
    assert by_name["Caching"].entity_type == "concept"
    # mention entities carry document/chunk metadata
    assert by_name["Alice"].metadata == {"document_id": "doc1", "chunk_id": "chunk1"}


def test_blank_and_colonless_lines_skipped():
    result = _extract("\n   \njust a sentence without a label\nPerson: Bob")
    assert [e.name for e in result.entities] == ["Bob"]


def test_depends_on_relation():
    result = _extract("Depends on: web -> db")
    rel = result.relations[0]
    assert rel.relation_type == "depends_on"
    assert (rel.source.name, rel.target.name) == ("web", "db")
    assert rel.source.entity_type == "system"
    # relation endpoints are non-mention entities
    assert rel.source.metadata.get("mention") == "false"


def test_defines_relation():
    result = _extract("Defines: TTL -> expiry window")
    rel = result.relations[0]
    assert rel.relation_type == "defines"
    assert rel.source.entity_type == "term"
    assert rel.target.entity_type == "concept"


def test_conflict_relation_split_case_insensitive():
    result = _extract("Conflict: cache-A Conflicts With cache-B")
    rel = result.relations[0]
    assert rel.relation_type == "conflicts_with"
    assert (rel.source.name, rel.target.name) == ("cache-A", "cache-B")


def test_repeated_name_is_deduped_to_one_entity():
    result = _extract("System: web\nDepends on: web -> db")
    web = [e for e in result.entities if e.name == "web"]
    assert len(web) == 1  # the labelled entity is reused by the relation


def test_normalize_entity_name_collapses_whitespace_and_casefolds():
    assert normalize_entity_name("  Web   Service\tNode ") == "web service node"


def test_validate_entity_type_accepts_supported_and_rejects_unknown():
    assert validate_entity_type("concept") == "concept"
    with pytest.raises(ValueError):
        validate_entity_type("planet")


def test_validate_relation_type_accepts_supported_and_rejects_unknown():
    assert validate_relation_type("depends_on") == "depends_on"
    with pytest.raises(ValueError):
        validate_relation_type("orbits")


def test_extracted_entity_normalized_name_property():
    assert ExtractedEntity(entity_type="concept", name="  Foo Bar ").normalized_name == "foo bar"


def test_extracted_entity_rejects_empty_name():
    with pytest.raises(ValueError):
        ExtractedEntity(entity_type="concept", name="   ")


def test_extracted_entity_rejects_unsupported_type():
    with pytest.raises(ValueError):
        ExtractedEntity(entity_type="planet", name="Mars")


def test_extracted_relation_rejects_blank_evidence():
    e = ExtractedEntity(entity_type="system", name="web")
    with pytest.raises(ValueError):
        ExtractedRelation(
            relation_type="depends_on",
            source=e,
            target=e,
            evidence_text="   ",
            chunk_id="c",
            document_id="d",
        )


def test_extracted_relation_rejects_unsupported_type():
    e = ExtractedEntity(entity_type="system", name="web")
    with pytest.raises(ValueError):
        ExtractedRelation(
            relation_type="orbits",
            source=e,
            target=e,
            evidence_text="web orbits db",
            chunk_id="c",
            document_id="d",
        )
