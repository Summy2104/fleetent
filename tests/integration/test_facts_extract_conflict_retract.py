"""Integration tests: cross-relation conflict retract via extract_facts + commit pipeline."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.memory import facts_store
from fleetent.memory.facts_models import Fact, RawFact, ResolvedFact, ClassifiedFact
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _open_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _seed_fact(fid: str, relation: str, obj: str, cardinality: str = "multi") -> Fact:
    now = _now()
    return Fact(
        fact_id=fid,
        user_id="u1",
        subject="user",
        relation=relation,
        object=obj,
        cardinality=cardinality,  # type: ignore[arg-type]
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
    )


async def test_conflict_forget_retracts_contradicting_fact(tmp_path: Path) -> None:
    """Forget directive from extract stage → contradicting fact retracted in DB."""
    from fleetent.memory import facts_commit, facts_pipeline

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]

    # Seed existing fact: user prefers Rust
    facts_store.insert_fact(_seed_fact("rust-pref", "prefers_language", "Rust"))

    # Simulate what run_pipeline does after extract: raws contain both the new
    # dislikes fact and the forget directive the LLM would emit given the snapshot.
    # We test commit_facts handles the forget relation regardless of the companion fact.
    classified: list[ClassifiedFact] = [
        ClassifiedFact(
            subject="user",
            relation="dislikes",
            object="Rust",
            temporal="none",
            cardinality="multi",
            verdict="Orthogonal",
            statement="用户不喜欢 Rust",
        ),
        ClassifiedFact(
            subject="user",
            relation="forget",
            object="Rust",
            temporal="none",
            cardinality="multi",
            verdict="Orthogonal",
            statement="忘记 prefers_language=Rust",
        ),
    ]
    facts_commit.commit_facts("u1", classified, db, source_turn="t1")

    # The old prefers_language=Rust fact should now be retracted
    old = facts_store.get_fact("rust-pref")
    assert old is not None
    assert old.status == "retracted", (
        f"Expected retracted, got {old.status!r} — cross-relation conflict not handled"
    )

    # The new dislikes=Rust fact should be active
    active = facts_store.list_active_facts("u1", subject="user")
    dislikes = [f for f in active if f.relation == "dislikes" and f.object == "Rust"]
    assert len(dislikes) == 1


async def test_active_facts_snapshot_injected_into_extract(tmp_path: Path) -> None:
    """extract_facts receives active_facts and appends snapshot to user message."""
    from fleetent.memory import facts_pipeline

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    facts_store.insert_fact(_seed_fact("rust-pref", "prefers_language", "Rust"))

    captured_messages: list[list[dict]] = []

    class _CaptureLLM:
        chat = None
        completions = None

        def __init__(self) -> None:
            self.chat = self
            self.completions = self

        async def create(self, **kwargs):
            captured_messages.append(kwargs.get("messages", []))

            class _Msg:
                content = "[]"

            class _Choice:
                message = _Msg()

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    active_facts = facts_store.list_active_facts("u1", subject="user")
    assert len(active_facts) == 1

    await facts_pipeline.extract_facts(
        turn_content="我不喜欢 Rust",
        llm_client=_CaptureLLM(),
        active_facts=active_facts,
    )

    assert len(captured_messages) == 1
    user_msg = next(m["content"] for m in captured_messages[0] if m["role"] == "user")
    assert "已有记忆" in user_msg
    assert "prefers_language" in user_msg
    assert "Rust" in user_msg


async def test_non_conflict_preserves_existing_fact(tmp_path: Path) -> None:
    """Forget not emitted → existing Rust preference stays active."""
    from fleetent.memory import facts_commit

    db = _open_db(tmp_path)
    facts_store.set_facts_db(db, None)  # type: ignore[arg-type]
    facts_store.insert_fact(_seed_fact("rust-pref", "prefers_language", "Rust"))

    # Only a new Go preference, no forget directive
    classified: list[ClassifiedFact] = [
        ClassifiedFact(
            subject="user",
            relation="prefers_language",
            object="Go",
            temporal="none",
            cardinality="multi",
            verdict="Orthogonal",
        ),
    ]
    facts_commit.commit_facts("u1", classified, db, source_turn="t2")

    old = facts_store.get_fact("rust-pref")
    assert old is not None
    assert old.status == "active", (
        f"Expected active, got {old.status!r} — non-conflict should not retract"
    )
