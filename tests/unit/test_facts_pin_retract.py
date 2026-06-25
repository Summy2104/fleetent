"""Unit-style tests for pin_fact / retract_fact via a fake store seam."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fleetent.memory.facts_models import Fact


def _fact(fid: str, status: str = "active", expires_at=None) -> Fact:
    now = datetime.now(UTC)
    return Fact(
        fact_id=fid,
        user_id="u1",
        subject="user",
        relation="has_skill",
        object="Python",
        cardinality="multi",
        status=status,  # type: ignore[arg-type]
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=expires_at,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )


async def test_pin_sets_expires_at_null(monkeypatch) -> None:
    from fleetent.memory import facts_lifecycle, facts_store

    store_state = {"f1": _fact("f1", "active", expires_at=datetime.now(UTC))}
    pinned: dict[str, object] = {}

    monkeypatch.setattr(facts_store, "get_fact", lambda fid: store_state.get(fid))
    monkeypatch.setattr(
        facts_store, "set_fact_expires_at", lambda fid, exp: pinned.__setitem__(fid, exp)
    )

    facts_lifecycle.pin_fact("f1")
    assert pinned["f1"] is None


async def test_pin_non_active_raises(monkeypatch) -> None:
    from fleetent.memory import facts_lifecycle, facts_store

    monkeypatch.setattr(facts_store, "get_fact", lambda fid: _fact(fid, "archived"))

    with pytest.raises(ValueError, match="non-active"):
        facts_lifecycle.pin_fact("f1")


async def test_retract_sets_status_and_deletes_vector(monkeypatch) -> None:
    from fleetent.memory import facts_lifecycle, facts_store

    monkeypatch.setattr(facts_store, "get_fact", lambda fid: _fact(fid, "active"))
    statuses: dict[str, str] = {}
    monkeypatch.setattr(
        facts_store, "update_fact_status", lambda fid, st: statuses.__setitem__(fid, st)
    )

    deleted: list[tuple[str, str]] = []

    class _Backend:
        async def delete(self, id, namespace):
            deleted.append((id, namespace))

    await facts_lifecycle.retract_fact("f1", vector_backend=_Backend())
    assert statuses["f1"] == "retracted"
    assert deleted and deleted[0][0] == "f1"


async def test_retract_by_relation(monkeypatch) -> None:
    from fleetent.memory import facts_lifecycle, facts_store

    facts = [_fact("a", "active"), _fact("b", "active")]
    monkeypatch.setattr(
        facts_store, "active_facts_for_relation", lambda u, s, r: facts
    )
    statuses: dict[str, str] = {}
    monkeypatch.setattr(
        facts_store, "update_fact_status", lambda fid, st: statuses.__setitem__(fid, st)
    )

    class _Backend:
        async def delete(self, id, namespace):
            pass

    await facts_lifecycle.retract_by_relation(
        "u1", "user", "has_skill", vector_backend=_Backend()
    )
    assert statuses == {"a": "retracted", "b": "retracted"}
