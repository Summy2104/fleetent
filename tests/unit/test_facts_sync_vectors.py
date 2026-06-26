"""Unit tests: sync_vectors upserts active facts and deletes superseded ones."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fleetent.memory.facts_models import Fact


class _FakeBackend:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, str]] = []
        self.deletes: list[tuple[str, str]] = []

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        self.upserts.append((id, namespace))

    async def delete(self, id: str, namespace: str) -> None:
        self.deletes.append((id, namespace))


def _fact(fid: str, status: str) -> Fact:
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
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )


async def test_sync_vectors_upserts_active_deletes_superseded(monkeypatch) -> None:
    from fleetent.memory import facts_commit

    async def _fake_embed(text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(facts_commit, "embed_text", _fake_embed)

    backend = _FakeBackend()
    await facts_commit.sync_vectors(
        "u1",
        new_active=[_fact("a", "active")],
        superseded_ids=["old"],
        vector_backend=backend,
    )

    assert ("a", "mem:u1") in backend.upserts
    assert ("old", "mem:u1") in backend.deletes


async def test_sync_vectors_failure_does_not_raise(monkeypatch) -> None:
    from fleetent.memory import facts_commit

    async def _fake_embed(text: str) -> list[float]:
        raise RuntimeError("embed down")

    monkeypatch.setattr(facts_commit, "embed_text", _fake_embed)

    backend = _FakeBackend()
    # Must not propagate — vector sync is best-effort post-commit.
    await facts_commit.sync_vectors(
        "u1",
        new_active=[_fact("a", "active")],
        superseded_ids=[],
        vector_backend=backend,
    )
