"""Pure helpers of KB graph search: alias parsing, relation expansion, dedupe, merge."""

import pytest

from fleetent.intelligence.knowledge_base.graph_search import (
    EntityRef,
    GraphSearchChunk,
    RelationRef,
    _add_candidate,
    _dedupe_entities,
    _dedupe_relations,
    _direct_mention_chunk_ids,
    _entities_by_id,
    _metadata_aliases,
    _related_entity_ids,
    _relations_for_entities,
    graph_search,
)
from fleetent.intelligence.knowledge_base.models import KnowledgeChunk


class _FakeDB:
    """Duck-typed SQLiteDatabase stub: execute(...) -> self, fetchall() -> canned rows."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.last_sql: str | None = None
        self.last_params: dict[str, object] | None = None

    def execute(self, sql: str, params: dict[str, object] | None = None) -> "_FakeDB":
        self.last_sql = sql
        self.last_params = params
        return self

    def fetchall(self) -> list[dict[str, object]]:
        return self._rows


def _chunk(cid: str = "c1") -> KnowledgeChunk:
    return KnowledgeChunk(
        id=cid,
        document_id="d1",
        tenant_id="t",
        kb_id="kb",
        filename="f.md",
        content="body",
        position=0,
        score=0.0,
        source="upload",
        source_url=None,
    )


def _rel(rid: str, rtype: str, src: str, tgt: str) -> RelationRef:
    return RelationRef(
        id=rid,
        relation_type=rtype,
        source_entity_id=src,
        target_entity_id=tgt,
        evidence_chunk_id="c1",
    )


def test_metadata_aliases_from_list():
    assert _metadata_aliases('{"aliases": ["Web Service", "WEB svc"]}') == [
        "web service",
        "web svc",
    ]


def test_metadata_aliases_from_comma_string():
    assert _metadata_aliases('{"aliases": "Foo, Bar"}') == ["foo", "bar"]


def test_metadata_aliases_missing_key_or_bad_json():
    assert _metadata_aliases("{}") == []
    assert _metadata_aliases("not json") == []
    assert _metadata_aliases('{"aliases": 42}') == []


def test_related_entity_ids_directional_default():
    rels = [_rel("r1", "depends_on", "a", "b")]
    assert _related_entity_ids(rels, {"a"}) == {"b"}
    # target-only match does not expand for a directional relation
    assert _related_entity_ids(rels, {"b"}) == set()


def test_related_entity_ids_symmetric_relations():
    rels = [_rel("r1", "related_to", "a", "b"), _rel("r2", "conflicts_with", "c", "d")]
    assert _related_entity_ids(rels, {"b"}) == {"a"}
    assert _related_entity_ids(rels, {"c"}) == {"d"}


def test_related_entity_ids_skips_mentions_and_matched():
    rels = [_rel("r1", "mentions", "a", "b"), _rel("r2", "depends_on", "a", "a")]
    # mentions ignored; self-relation removed because result subtracts matched ids
    assert _related_entity_ids(rels, {"a"}) == set()


def test_dedupe_entities_and_relations_by_id():
    e = EntityRef(id="e1", entity_type="system", name="web", normalized_name="web")
    assert _dedupe_entities([e, e]) == [e]
    r = _rel("r1", "depends_on", "a", "b")
    assert _dedupe_relations([r, r]) == [r]


async def test_graph_search_rejects_unsupported_depth():
    # the depth guard runs before any store/runtime access — a pure, fast rejection
    with pytest.raises(ValueError):
        await graph_search("q", depth=2)


def test_direct_mention_chunk_ids_empty_and_mapped():
    assert _direct_mention_chunk_ids(_FakeDB([]), "t", ["kb"], {}) == []
    db = _FakeDB([{"chunk_id": "c2"}, {"chunk_id": "c1"}])
    e = EntityRef(id="e1", entity_type="system", name="web", normalized_name="web")
    out = _direct_mention_chunk_ids(db, "t", ["kb"], {"e1": e})
    assert out == ["c2", "c1"]
    assert db.last_params["tenant_id"] == "t"
    assert db.last_params["entity_id_0"] == "e1"


def test_relations_for_entities_empty_and_mapped():
    assert _relations_for_entities(_FakeDB([]), "t", ["kb"], set()) == []
    db = _FakeDB(
        [
            {
                "id": "r1",
                "relation_type": "depends_on",
                "source_entity_id": "a",
                "target_entity_id": "b",
                "evidence_chunk_id": "c1",
            }
        ]
    )
    rels = _relations_for_entities(db, "t", ["kb"], {"a"})
    assert rels == [_rel("r1", "depends_on", "a", "b")]


def test_entities_by_id_empty_and_mapped():
    assert _entities_by_id(_FakeDB([]), set()) == {}
    db = _FakeDB([{"id": "e1", "entity_type": "system", "name": "Web", "normalized_name": "web"}])
    out = _entities_by_id(db, {"e1"})
    assert out["e1"] == EntityRef(id="e1", entity_type="system", name="Web", normalized_name="web")


def test_add_candidate_inserts_then_merges_keeping_max_score():
    candidates: dict[str, GraphSearchChunk] = {}
    e1 = EntityRef(id="e1", entity_type="system", name="web", normalized_name="web")
    _add_candidate(
        candidates,
        _chunk("c1"),
        score=0.4,
        reason="direct_entity_match",
        entities=[e1],
        relations=[],
        evidence_chunk_ids=["c1"],
    )
    assert candidates["c1"].graph_score == 0.4

    e2 = EntityRef(id="e2", entity_type="term", name="ttl", normalized_name="ttl")
    _add_candidate(
        candidates,
        _chunk("c1"),
        score=0.9,
        reason="relation_evidence",
        entities=[e2],
        relations=[_rel("r1", "defines", "e2", "e1")],
        evidence_chunk_ids=["c2"],
    )
    merged = candidates["c1"]
    assert merged.graph_score == 0.9  # max kept
    assert merged.reason == "relation_evidence"  # higher score's reason wins
    assert {e.id for e in merged.matched_entities} == {"e1", "e2"}
    assert merged.evidence_chunk_ids == ["c1", "c2"]
