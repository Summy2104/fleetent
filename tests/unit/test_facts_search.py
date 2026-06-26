"""Unit tests: search_facts vector retrieval + max_score gate + access update."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fleetent.memory.facts_models import Fact
from fleetent.vector_store.backend import SearchResult as VectorHit


def _fact(fid: str, status: str = "active", **over) -> Fact:
    now = datetime.now(UTC).replace(microsecond=0)
    base = dict(
        fact_id=fid,
        user_id="u1",
        subject="user",
        relation="has_skill",
        object="Python",
        cardinality="multi",
        status=status,
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )
    base.update(over)
    return Fact(**base)  # type: ignore[arg-type]


class _FakeBackend:
    def __init__(self, hits: list[VectorHit]) -> None:
        self._hits = hits

    async def search(self, vector, namespace, limit=10):
        return self._hits[:limit]


def _patch_common(monkeypatch, facts_search, hits, by_id):
    async def _fake_embed(text):
        return [0.1, 0.2]

    monkeypatch.setattr(facts_search, "embed_text", _fake_embed)
    monkeypatch.setattr(facts_search, "_facts_by_ids", lambda ids: by_id)


async def test_search_filters_non_active(monkeypatch) -> None:
    from fleetent.memory import facts_search

    hits = [VectorHit(id="a", score=0.9), VectorHit(id="b", score=0.8)]
    by_id = {"a": _fact("a", "active"), "b": _fact("b", "superseded")}
    _patch_common(monkeypatch, facts_search, hits, by_id)
    monkeypatch.setattr(facts_search, "_update_access", lambda *a, **k: None)

    results = await facts_search.search_facts(
        "u1", "skills", limit=5, vector_backend=_FakeBackend(hits)
    )
    ids = [r.fact.fact_id for r in results]
    assert ids == ["a"]


async def test_search_filters_by_subject(monkeypatch) -> None:
    from fleetent.memory import facts_search

    # Same user-memory space holds facts about both the user and the agent;
    # a subject filter must return only the requested subject's facts.
    hits = [VectorHit(id="u", score=0.9), VectorHit(id="a", score=0.88)]
    by_id = {
        "u": _fact("u", "active", subject="user", relation="name", object="程鑫"),
        "a": _fact("a", "active", subject="agent", relation="name", object="小派"),
    }
    _patch_common(monkeypatch, facts_search, hits, by_id)
    monkeypatch.setattr(facts_search, "_update_access", lambda *a, **k: None)

    results = await facts_search.search_facts(
        "u1", "名字", limit=5, subject="user", vector_backend=_FakeBackend(hits)
    )
    assert [r.fact.fact_id for r in results] == ["u"]
    assert results[0].fact.object == "程鑫"


async def test_search_no_subject_filter_returns_all_subjects(monkeypatch) -> None:
    from fleetent.memory import facts_search

    hits = [VectorHit(id="u", score=0.9), VectorHit(id="a", score=0.88)]
    by_id = {
        "u": _fact("u", "active", subject="user"),
        "a": _fact("a", "active", subject="agent"),
    }
    _patch_common(monkeypatch, facts_search, hits, by_id)
    monkeypatch.setattr(facts_search, "_update_access", lambda *a, **k: None)

    results = await facts_search.search_facts(
        "u1", "q", limit=5, vector_backend=_FakeBackend(hits)
    )
    assert {r.fact.fact_id for r in results} == {"u", "a"}


async def test_max_score_below_threshold_skips_access(monkeypatch) -> None:
    from fleetent.memory import facts_search

    hits = [VectorHit(id="a", score=0.41)]
    by_id = {"a": _fact("a", "active")}
    _patch_common(monkeypatch, facts_search, hits, by_id)

    called = {"update": False}
    monkeypatch.setattr(
        facts_search, "_update_access", lambda *a, **k: called.__setitem__("update", True)
    )

    await facts_search.search_facts("u1", "weather", limit=5, vector_backend=_FakeBackend(hits))
    assert called["update"] is False


async def test_max_score_at_or_above_threshold_updates_access(monkeypatch) -> None:
    from fleetent.memory import facts_search

    hits = [VectorHit(id="a", score=0.82)]
    by_id = {"a": _fact("a", "active")}
    _patch_common(monkeypatch, facts_search, hits, by_id)

    updated_ids: list[str] = []
    monkeypatch.setattr(
        facts_search, "_update_access", lambda ids, now: updated_ids.extend(ids)
    )

    await facts_search.search_facts("u1", "skills", limit=5, vector_backend=_FakeBackend(hits))
    assert "a" in updated_ids


async def test_max_score_exactly_threshold_updates_access(monkeypatch) -> None:
    from fleetent.memory import facts_search

    hits = [VectorHit(id="a", score=0.5)]
    by_id = {"a": _fact("a", "active")}
    _patch_common(monkeypatch, facts_search, hits, by_id)

    updated_ids: list[str] = []
    monkeypatch.setattr(facts_search, "_update_access", lambda ids, now: updated_ids.extend(ids))

    await facts_search.search_facts("u1", "skills", limit=5, vector_backend=_FakeBackend(hits))
    assert "a" in updated_ids
