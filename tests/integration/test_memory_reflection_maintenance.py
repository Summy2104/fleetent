from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from fleetent.db import SQLiteDatabase
from tests.integration.test_migrations import apply_migrations


def _use_db(monkeypatch, db_path) -> None:
    """Point env + reflection state at an Alembic-migrated db.

    reflection no longer falls back to DATABASE_URL (agent-runtime-db-routing-cleanup), so
    its per-agent state DB must be injected; DATABASE_URL stays set for memory/traces.
    """
    from fleetent import reflection
    from fleetent.memory import store as memory_store

    db_handle = SQLiteDatabase(path=db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(reflection, "_state_db", db_handle)
    monkeypatch.setattr(memory_store, "_state_db", db_handle)


async def test_memory_candidate_generates_pending_proposal_without_modifying_memory(
    tmp_path,
    monkeypatch,
):
    from fleetent import observability, reflection

    db_path = tmp_path / "reflection_maintenance.db"
    apply_migrations(db_path)
    _use_db(monkeypatch, db_path)
    before = _memory_rows(db_path)
    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers Python for backend work"},
            user_id="user-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers Python for backend work"},
            user_id="user-1",
        ),
    ]
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=[]))

    report = await reflection.run_reflection("user-1")
    proposals = reflection.generate_memory_maintenance_proposals("user-1", report.findings)

    assert _memory_rows(db_path) == before
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.action == "rewrite"
    assert proposal.user_id == "user-1"
    assert proposal.status == "pending"
    assert proposal.proposed_content == "User prefers Python for backend work"
    assert proposal.metadata_patch["confirmation"] == "inline"


async def test_memory_conflict_generates_owner_review_proposal_without_memory_write(
    tmp_path,
    monkeypatch,
):
    from fleetent import memory as memory_layer
    from fleetent import observability, reflection

    db_path = tmp_path / "reflection_maintenance.db"
    apply_migrations(db_path)
    now = datetime.now(UTC)
    with sqlite3.connect(db_path) as conn:
        for memory_id, content in [
            ("mem-1", "User location is Shanghai"),
            ("mem-2", "User location is Beijing"),
        ]:
            conn.execute(
                """
                INSERT INTO memory_items (
                    id, user_id, type, content, created_at, updated_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    "user-1",
                    "identity",
                    content,
                    now.isoformat(),
                    now.isoformat(),
                    None,
                ),
            )
    before = _memory_rows(db_path)
    memories = [
        memory_layer.MemoryItem(
            id="mem-1",
            user_id="user-1",
            type="identity",
            content="User location is Shanghai",
            created_at=now,
            updated_at=now,
            expires_at=None,
        ),
        memory_layer.MemoryItem(
            id="mem-2",
            user_id="user-1",
            type="identity",
            content="User location is Beijing",
            created_at=now,
            updated_at=now,
            expires_at=None,
        ),
    ]
    _use_db(monkeypatch, db_path)
    monkeypatch.setattr(
        observability,
        "query_trace_events",
        lambda query: [
            observability.TraceEvent(
                id="trace-1",
                run_id="run-1",
                event_type="agent_run_completed",
                payload={"user_input": "remember my profile"},
                user_id="user-1",
            )
        ],
    )
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=memories))

    report = await reflection.run_reflection("user-1")
    proposals = reflection.generate_memory_maintenance_proposals("user-1", report.findings)

    assert _memory_rows(db_path) == before
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.action == "merge"
    assert proposal.target_memory_ids == ["mem-1", "mem-2"]
    assert proposal.risk == "medium"
    assert proposal.metadata_patch["confirmation"] == "review"


async def test_team_or_project_fact_suggests_shared_memory_or_kb(tmp_path, monkeypatch):
    from fleetent import observability, reflection

    db_path = tmp_path / "reflection_maintenance.db"
    apply_migrations(db_path)
    _use_db(monkeypatch, db_path)
    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"memory_fact": "Team uses GitHub Flow for releases"},
            user_id="user-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"memory_fact": "Team uses GitHub Flow for releases"},
            user_id="user-1",
        ),
    ]
    monkeypatch.setattr(observability, "query_trace_events", lambda query: events)
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=[]))

    report = await reflection.run_reflection("user-1")
    proposals = reflection.generate_memory_maintenance_proposals("user-1", report.findings)

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.action == "suggest_shared_memory_or_kb"
    assert proposal.target_memory_ids == []
    assert proposal.risk == "low"
    assert "not_user_memory" in proposal.metadata_patch["boundary"]


async def test_memory_layer_public_mutation_rejects_cross_user_target(tmp_path, monkeypatch):
    from fleetent import memory as memory_layer

    db_path = tmp_path / "reflection_maintenance.db"
    apply_migrations(db_path)
    now = datetime.now(UTC)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "mem-1",
                "user-1",
                "preferences",
                "User prefers Python",
                now.isoformat(),
                now.isoformat(),
                None,
            ),
        )
    _use_db(monkeypatch, db_path)

    with pytest.raises(ValueError, match="does not exist for user"):
        await memory_layer.update_user_memory_content(
            "user-2",
            "mem-1",
            "User prefers Go",
        )

    assert _memory_rows(db_path)[0][3] == "User prefers Python"


def _memory_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT id, user_id, type, content, expires_at FROM memory_items ORDER BY id"
        ).fetchall()
