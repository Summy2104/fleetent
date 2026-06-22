"""Pure helpers of KB graph search: alias parsing, relation expansion, dedupe, merge."""

from contextlib import suppress

import pytest

from fleetent.knowledge_base.models import KnowledgeChunk
from fleetent.knowledge_base.retrieval.graph_search import (
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


class _FakeStore:
    def __init__(self, chunks: list[KnowledgeChunk]) -> None:
        self._chunks = {chunk.id: chunk for chunk in chunks}

    def get_chunks_by_ids(self, _tenant_id: str, chunk_ids: list[str]) -> list[KnowledgeChunk]:
        return [self._chunks[chunk_id] for chunk_id in chunk_ids if chunk_id in self._chunks]


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


def _monotonic(values: list[float]):
    last = values[-1]
    remaining = iter(values)

    def _fake() -> float:
        nonlocal last
        with suppress(StopIteration):
            last = next(remaining)
        return last

    return _fake


async def test_graph_search_records_kb_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.knowledge_base.retrieval import graph_search as graph_search_module
    from fleetent.observability import KBRetrievalAuditContext

    captured: list[dict[str, object]] = []
    entity = EntityRef(id="e1", entity_type="system", name="Web", normalized_name="web")
    chunk = _chunk("c1")

    monkeypatch.setattr(graph_search_module.time, "monotonic", _monotonic([30.0, 30.008]))
    monkeypatch.setattr(graph_search_module, "_database", lambda: _FakeDB([]))
    monkeypatch.setattr(graph_search_module, "match_entities", lambda *_args, **_kwargs: [entity])
    monkeypatch.setattr(
        graph_search_module,
        "_direct_mention_chunk_ids",
        lambda *_args, **_kwargs: ["c1"],
    )
    monkeypatch.setattr(
        graph_search_module,
        "record_kb_retrieval",
        lambda context, **kwargs: captured.append({"context": context, **kwargs}),
    )

    result = await graph_search_module.graph_search(
        "web service",
        tenant_id="tenant-a",
        kb_ids=["kb-1"],
        store=_FakeStore([chunk]),
        audit_context=KBRetrievalAuditContext(
            run_id="run-1",
            session_id="sess-1",
            user_id="user-1",
            agent_name="agent-1",
            tenant_id="tenant-a",
        ),
    )

    assert [item.chunk.id for item in result.chunks] == ["c1"]
    assert len(captured) == 1
    assert captured[0]["mode"] == "graph"
    assert captured[0]["query"] == "web service"
    assert captured[0]["kb_ids"] == ["kb-1"]
    assert captured[0]["latency_ms"] == pytest.approx(8.0)
    assert [chunk.id for chunk in captured[0]["results"]] == ["c1"]


async def test_graph_search_records_empty_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.knowledge_base.retrieval import graph_search as graph_search_module
    from fleetent.observability import KBRetrievalAuditContext

    captured: list[dict[str, object]] = []

    monkeypatch.setattr(graph_search_module.time, "monotonic", _monotonic([40.0, 40.003]))
    monkeypatch.setattr(graph_search_module, "_database", lambda: _FakeDB([]))
    monkeypatch.setattr(graph_search_module, "match_entities", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        graph_search_module,
        "record_kb_retrieval",
        lambda context, **kwargs: captured.append({"context": context, **kwargs}),
    )

    result = await graph_search_module.graph_search(
        "no match",
        tenant_id="tenant-a",
        kb_ids=["kb-1"],
        store=_FakeStore([]),
        audit_context=KBRetrievalAuditContext(run_id="run-2", tenant_id="tenant-a"),
    )

    assert result.chunks == []
    assert len(captured) == 1
    assert captured[0]["results"] == []


async def test_graph_search_swallows_audit_helper_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.knowledge_base.retrieval import graph_search as graph_search_module
    from fleetent.observability import KBRetrievalAuditContext

    entity = EntityRef(id="e1", entity_type="system", name="Web", normalized_name="web")
    chunk = _chunk("c1")

    monkeypatch.setattr(graph_search_module, "_database", lambda: _FakeDB([]))
    monkeypatch.setattr(graph_search_module, "match_entities", lambda *_args, **_kwargs: [entity])
    monkeypatch.setattr(
        graph_search_module,
        "_direct_mention_chunk_ids",
        lambda *_args, **_kwargs: ["c1"],
    )
    monkeypatch.setattr(
        graph_search_module,
        "record_kb_retrieval",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit down")),
    )

    result = await graph_search_module.graph_search(
        "web service",
        tenant_id="tenant-a",
        kb_ids=["kb-1"],
        store=_FakeStore([chunk]),
        audit_context=KBRetrievalAuditContext(run_id="run-3", tenant_id="tenant-a"),
    )

    assert [item.chunk.id for item in result.chunks] == ["c1"]
