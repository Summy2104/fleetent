"""Unit tests: always-scope facts — list_always_facts + soft eviction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fleetent.memory.facts_models import Fact


def _fact(fid: str, relation: str = "has_skill", scope: str = "situational", status: str = "active", **over) -> Fact:
    now = datetime.now(UTC).replace(microsecond=0)
    base = dict(
        fact_id=fid,
        user_id="u1",
        subject="user",
        relation=relation,
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
        scope=scope,
    )
    base.update(over)
    return Fact(**base)  # type: ignore[arg-type]


# ── list_always_facts ─────────────────────────────────────────────────────────


def test_list_always_facts_returns_always_active(monkeypatch) -> None:
    from fleetent.memory import facts_store

    facts = [
        _fact("a1", relation="response_style", scope="always"),
        _fact("a2", relation="tone", scope="always"),
        _fact("s1", relation="has_skill", scope="situational"),
    ]
    monkeypatch.setattr(
        facts_store,
        "_facts_database",
        lambda: _FakeDB([f for f in facts if f.scope == "always" and f.status == "active"]),
    )

    result = facts_store.list_always_facts("u1")
    assert [f.fact_id for f in result] == ["a1", "a2"]


def test_list_always_facts_excludes_non_active(monkeypatch) -> None:
    from fleetent.memory import facts_store

    facts = [
        _fact("a1", relation="response_style", scope="always"),
        _fact("a2", relation="tone", scope="always", status="retracted"),
    ]
    monkeypatch.setattr(
        facts_store,
        "_facts_database",
        lambda: _FakeDB([f for f in facts if f.scope == "always" and f.status == "active"]),
    )

    result = facts_store.list_always_facts("u1")
    assert [f.fact_id for f in result] == ["a1"]


def test_list_always_facts_returns_empty_when_none(monkeypatch) -> None:
    from fleetent.memory import facts_store

    monkeypatch.setattr(facts_store, "_facts_database", lambda: _FakeDB([]))
    result = facts_store.list_always_facts("u1")
    assert result == []


def test_list_always_facts_does_not_call_vector_backend(monkeypatch) -> None:
    from fleetent.memory import facts_store

    called = []

    class _SpyBackend:
        async def search(self, *a, **k):
            called.append("search")
            return []

    monkeypatch.setattr(facts_store, "_facts_database", lambda: _FakeDB([]))
    monkeypatch.setattr(facts_store, "_facts_vector_backend", _SpyBackend())

    facts_store.list_always_facts("u1")
    assert called == [], "list_always_facts must not call vector backend"


# ── soft eviction ─────────────────────────────────────────────────────────────


def test_soft_eviction_not_triggered_below_limit(monkeypatch) -> None:
    """Under the soft cap — no eviction."""
    from fleetent.memory import facts_store

    retracted: list[str] = []
    monkeypatch.setattr(facts_store, "_count_soft_always_facts", lambda uid: 14)
    monkeypatch.setattr(facts_store, "update_fact_status", lambda fid, status: retracted.append(fid))
    monkeypatch.setattr(facts_store, "_oldest_soft_always_fact_id", lambda uid: "old1")

    facts_store._maybe_evict_soft_always(user_id="u1", relation="tone")
    assert retracted == []


def test_soft_eviction_triggered_at_limit(monkeypatch) -> None:
    """At cap — oldest soft fact is retracted."""
    from fleetent.memory import facts_store

    retracted: list[str] = []
    monkeypatch.setattr(facts_store, "_count_soft_always_facts", lambda uid: 15)
    monkeypatch.setattr(facts_store, "update_fact_status", lambda fid, status: retracted.append(fid))
    monkeypatch.setattr(facts_store, "_oldest_soft_always_fact_id", lambda uid: "old1")

    facts_store._maybe_evict_soft_always(user_id="u1", relation="tone")
    assert retracted == ["old1"]


def test_soft_eviction_skipped_for_hard_relation(monkeypatch) -> None:
    """Hard relation — eviction never triggered regardless of count."""
    from fleetent.memory import facts_store

    retracted: list[str] = []
    monkeypatch.setattr(facts_store, "_count_soft_always_facts", lambda uid: 15)
    monkeypatch.setattr(facts_store, "update_fact_status", lambda fid, status: retracted.append(fid))
    monkeypatch.setattr(facts_store, "_oldest_soft_always_fact_id", lambda uid: "old1")

    facts_store._maybe_evict_soft_always(user_id="u1", relation="never_do")
    assert retracted == []


def test_soft_eviction_skipped_for_unknown_relation(monkeypatch) -> None:
    """Unknown relation defaults to hard — not evicted."""
    from fleetent.memory import facts_store

    retracted: list[str] = []
    monkeypatch.setattr(facts_store, "_count_soft_always_facts", lambda uid: 15)
    monkeypatch.setattr(facts_store, "update_fact_status", lambda fid, status: retracted.append(fid))
    monkeypatch.setattr(facts_store, "_oldest_soft_always_fact_id", lambda uid: "old1")

    facts_store._maybe_evict_soft_always(user_id="u1", relation="some_unknown_llm_invented_relation")
    assert retracted == []


# ── helpers ───────────────────────────────────────────────────────────────────


class _FakeDB:
    """Minimal DB stub: returns pre-built Fact rows from list_always_facts query."""

    def __init__(self, facts: list[Fact]) -> None:
        self._facts = facts

    def execute(self, sql: str, params: dict) -> "_FakeResult":
        return _FakeResult(self._facts)


class _FakeResult:
    def __init__(self, facts: list[Fact]) -> None:
        self._facts = facts

    def fetchall(self) -> list[dict]:
        from fleetent.memory._datetime_utils import format_datetime

        rows = []
        for f in self._facts:
            rows.append({
                "fact_id": f.fact_id,
                "user_id": f.user_id,
                "subject": f.subject,
                "relation": f.relation,
                "object": f.object,
                "cardinality": f.cardinality,
                "status": f.status,
                "access_count": f.access_count,
                "first_accessed_at": format_datetime(f.first_accessed_at),
                "last_accessed_at": format_datetime(f.last_accessed_at),
                "expires_at": format_datetime(f.expires_at),
                "valid_until": format_datetime(f.valid_until),
                "created_at": format_datetime(f.created_at),
                "updated_at": format_datetime(f.updated_at),
                "source_turn": f.source_turn,
                "statement": f.statement,
                "scope": f.scope,
            })
        return rows
