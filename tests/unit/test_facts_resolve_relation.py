"""Unit tests: resolve_relation merges a raw relation into the relation_clusters wordlist."""

from __future__ import annotations

import pytest

from fleetent.memory.facts_models import RawFact


class _FakeStore:
    """In-memory stand-in for facts_store relation_cluster functions."""

    def __init__(self, clusters: dict[str, tuple[str, bytes | None]]) -> None:
        # relation -> (cardinality, embedding)
        self._clusters = clusters
        self.inserted: list[tuple[str, str]] = []
        self.embedding_updates: dict[str, bytes] = {}

    def list_relation_clusters(self):
        from datetime import UTC, datetime

        from fleetent.memory.facts_models import RelationCluster

        now = datetime.now(UTC)
        return [
            RelationCluster(relation=r, cardinality=c, embedding=e, created_at=now)  # type: ignore[arg-type]
            for r, (c, e) in self._clusters.items()
        ]

    def get_relation_cluster(self, relation: str):
        from datetime import UTC, datetime

        from fleetent.memory.facts_models import RelationCluster

        if relation not in self._clusters:
            return None
        c, e = self._clusters[relation]
        return RelationCluster(
            relation=relation, cardinality=c, embedding=e, created_at=datetime.now(UTC)  # type: ignore[arg-type]
        )

    def insert_relation_cluster(self, cluster) -> None:
        self._clusters[cluster.relation] = (cluster.cardinality, cluster.embedding)
        self.inserted.append((cluster.relation, cluster.cardinality))

    def set_relation_cluster_embedding(self, relation: str, embedding: bytes) -> None:
        self.embedding_updates[relation] = embedding
        c, _ = self._clusters[relation]
        self._clusters[relation] = (c, embedding)


async def test_resolve_relation_empty_wordlist_inserts_new(monkeypatch) -> None:
    from fleetent.memory import facts_pipeline

    store = _FakeStore(clusters={})

    async def _fake_embed(text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    async def _fake_cardinality(relation: str, _client) -> str:
        return "multi"

    monkeypatch.setattr(facts_pipeline, "embed_text", _fake_embed)
    monkeypatch.setattr(facts_pipeline, "_judge_cardinality", _fake_cardinality)

    raw = RawFact(subject="user", relation="brand_new_rel", object="x", temporal="none")
    resolved = await facts_pipeline.resolve_relation(raw, store, llm_client=None)

    assert resolved.relation == "brand_new_rel"
    assert resolved.cardinality == "multi"
    assert ("brand_new_rel", "multi") in store.inserted


async def test_resolve_relation_high_cosine_merges(monkeypatch) -> None:
    from fleetent.memory import facts_pipeline

    # Existing cluster "prefers_language" with embedding aligned to query vector.
    existing_vec = facts_pipeline._vector_to_blob([1.0, 0.0, 0.0])
    store = _FakeStore(clusters={"prefers_language": ("single", existing_vec)})

    async def _fake_embed(text: str) -> list[float]:
        # cosine with [1,0,0] ~ 0.9999 (>= 0.90)
        return [0.999, 0.01, 0.0]

    monkeypatch.setattr(facts_pipeline, "embed_text", _fake_embed)

    raw = RawFact(subject="user", relation="uses_language", object="Go", temporal="none")
    resolved = await facts_pipeline.resolve_relation(raw, store, llm_client=None)

    assert resolved.relation == "prefers_language"
    assert resolved.cardinality == "single"
    assert store.inserted == []  # merged, not created


async def test_resolve_relation_low_cosine_creates_new(monkeypatch) -> None:
    from fleetent.memory import facts_pipeline

    existing_vec = facts_pipeline._vector_to_blob([1.0, 0.0, 0.0])
    store = _FakeStore(clusters={"prefers_language": ("single", existing_vec)})

    async def _fake_embed(text: str) -> list[float]:
        # orthogonal vector -> cosine ~ 0 (< 0.90)
        return [0.0, 1.0, 0.0]

    async def _fake_cardinality(relation: str, _client) -> str:
        return "multi"

    monkeypatch.setattr(facts_pipeline, "embed_text", _fake_embed)
    monkeypatch.setattr(facts_pipeline, "_judge_cardinality", _fake_cardinality)

    raw = RawFact(subject="user", relation="mentors", object="Bob", temporal="none")
    resolved = await facts_pipeline.resolve_relation(raw, store, llm_client=None)

    assert resolved.relation == "mentors"
    assert resolved.cardinality == "multi"
    assert ("mentors", "multi") in store.inserted


async def test_resolve_rename_relation_passes_through(monkeypatch) -> None:
    from fleetent.memory import facts_pipeline

    # renamed_to is a directive, not a real relation: it must pass through without
    # embedding/merging and never enter the wordlist.
    store = _FakeStore(clusters={})

    async def _boom(text):
        raise AssertionError("embed_text must not be called for renamed_to")

    monkeypatch.setattr(facts_pipeline, "embed_text", _boom)

    raw = RawFact(subject="张三", relation="renamed_to", object="张洋", temporal="none")
    resolved = await facts_pipeline.resolve_relation(raw, store, llm_client=None)

    assert resolved.relation == "renamed_to"
    assert resolved.subject == "张三"
    assert resolved.object == "张洋"
    assert store.inserted == []  # not added to the wordlist
