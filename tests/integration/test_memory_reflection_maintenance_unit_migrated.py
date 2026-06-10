from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.memory import extraction, store as memory_store
from tests.integration.test_migrations import apply_migrations


def _db_url(db_path) -> str:
    return f"sqlite:///{db_path}"


def test_memory_maintenance_public_api_is_importable():
    from fleetent.reflection import (
        AutoMaintenancePolicy,
        MemoryMaintenanceProposal,
        create_memory_maintenance_proposal,
    )

    proposal = MemoryMaintenanceProposal(
        id="proposal-1",
        user_id="user-1",
        action="rewrite",
        target_memory_ids=["mem-1"],
        proposed_content="User prefers Python.",
        metadata_patch={},
        risk="medium",
        reason="clarify wording",
        evidence_ids=["trace-1"],
        status="pending",
        created_at=datetime(2026, 6, 2, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, tzinfo=UTC),
        expires_at=None,
    )

    assert proposal.user_id == "user-1"
    assert AutoMaintenancePolicy().allow_low_risk is False
    assert callable(create_memory_maintenance_proposal)


def test_migration_creates_memory_maintenance_proposals_table(tmp_path):
    db_path = tmp_path / "maintenance.db"

    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(memory_maintenance_proposals)")
        }
        indexes = {
            row[1] for row in conn.execute("PRAGMA index_list(memory_maintenance_proposals)")
        }

    assert columns >= {
        "id",
        "user_id",
        "action",
        "target_memory_ids_json",
        "proposed_content",
        "metadata_patch_json",
        "risk",
        "reason",
        "evidence_ids_json",
        "status",
        "created_at",
        "updated_at",
        "expires_at",
    }
    assert "idx_memory_maintenance_user_status" in indexes


def test_create_proposal_defaults_to_pending_and_persists_json_fields(tmp_path, monkeypatch):
    from fleetent import reflection

    db_path = tmp_path / "maintenance.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="rewrite",
        target_memory_ids=["mem-1"],
        proposed_content="User prefers Python.",
        risk="medium",
        reason="clarify wording",
        evidence_ids=["trace-1"],
        metadata_patch={"interaction": "inline_confirmation"},
    )

    assert proposal.status == "pending"
    assert proposal.user_id == "user-1"
    assert proposal.target_memory_ids == ["mem-1"]
    assert proposal.metadata_patch == {"interaction": "inline_confirmation"}
    loaded = reflection.get_memory_maintenance_proposal(proposal.id)
    assert loaded == proposal


def test_pending_proposal_can_be_approved_or_rejected(tmp_path, monkeypatch):
    from fleetent import reflection

    db_path = tmp_path / "maintenance.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    approved = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="rewrite",
        target_memory_ids=["mem-1"],
        proposed_content="User prefers Python.",
        risk="medium",
        reason="clarify wording",
        evidence_ids=["trace-1"],
    )
    rejected = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="rewrite",
        target_memory_ids=["mem-2"],
        proposed_content="User prefers Go.",
        risk="medium",
        reason="clarify wording",
        evidence_ids=["trace-2"],
    )

    assert (
        reflection.approve_memory_maintenance_proposal(approved.id, actor_user_id="user-1").status
        == "approved"
    )
    assert (
        reflection.reject_memory_maintenance_proposal(rejected.id, actor_user_id="user-1").status
        == "rejected"
    )


@pytest.mark.parametrize("status", ["rejected", "expired"])
async def test_rejected_or_expired_proposal_cannot_apply(tmp_path, monkeypatch, status):
    from fleetent import reflection

    db_path = tmp_path / "maintenance.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    update_memory = AsyncMock()
    monkeypatch.setattr(reflection.memory, "update_user_memory_content", update_memory)
    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="rewrite",
        target_memory_ids=["mem-1"],
        proposed_content="User prefers Python.",
        risk="medium",
        reason="clarify wording",
        evidence_ids=["trace-1"],
    )
    if status == "rejected":
        reflection.reject_memory_maintenance_proposal(proposal.id, actor_user_id="user-1")
    else:
        reflection.expire_memory_maintenance_proposal(proposal.id)

    with pytest.raises(ValueError, match=status):
        await reflection.apply_memory_maintenance_proposal(
            proposal.id,
            actor_user_id="user-1",
        )

    update_memory.assert_not_awaited()


async def test_apply_approved_proposal_updates_status_to_applied(tmp_path, monkeypatch):
    from fleetent import reflection

    db_path = tmp_path / "maintenance.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    update_memory = AsyncMock()
    monkeypatch.setattr(reflection.memory, "update_user_memory_content", update_memory)
    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="rewrite",
        target_memory_ids=["mem-1"],
        proposed_content="User prefers Python.",
        risk="medium",
        reason="clarify wording",
        evidence_ids=["trace-1"],
    )
    reflection.approve_memory_maintenance_proposal(proposal.id, actor_user_id="user-1")

    applied = await reflection.apply_memory_maintenance_proposal(
        proposal.id,
        actor_user_id="user-1",
    )

    assert applied.status == "applied"
    update_memory.assert_awaited_once_with("user-1", "mem-1", "User prefers Python.")


async def test_apply_requires_owner_for_default_path(tmp_path, monkeypatch):
    from fleetent import reflection

    db_path = tmp_path / "maintenance.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    delete_memory = AsyncMock()
    monkeypatch.setattr(reflection.memory, "delete_user_memory", delete_memory)
    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="delete",
        target_memory_ids=["mem-1"],
        proposed_content=None,
        risk="high",
        reason="user asked to forget",
        evidence_ids=["trace-1"],
    )
    reflection.approve_memory_maintenance_proposal(proposal.id, actor_user_id="user-1")

    with pytest.raises(PermissionError, match="owner"):
        await reflection.apply_memory_maintenance_proposal(
            proposal.id,
            actor_user_id="admin-1",
        )

    delete_memory.assert_not_awaited()


async def test_high_risk_delete_cannot_be_auto_applied(tmp_path, monkeypatch):
    from fleetent import reflection

    db_path = tmp_path / "maintenance.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    delete_memory = AsyncMock()
    monkeypatch.setattr(reflection.memory, "delete_user_memory", delete_memory)
    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="delete",
        target_memory_ids=["mem-1"],
        proposed_content=None,
        risk="high",
        reason="low confidence conflict",
        evidence_ids=["trace-1"],
    )

    with pytest.raises(PermissionError, match="approval"):
        await reflection.apply_memory_maintenance_proposal(
            proposal.id,
            auto_policy=reflection.AutoMaintenancePolicy(allow_low_risk=True),
        )

    delete_memory.assert_not_awaited()


async def test_low_risk_mark_stale_can_auto_apply_when_policy_enabled(tmp_path, monkeypatch):
    from fleetent import reflection

    db_path = tmp_path / "maintenance.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    mark_stale = AsyncMock()
    monkeypatch.setattr(reflection.memory, "mark_user_memory_stale", mark_stale)
    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="mark_stale",
        target_memory_ids=["mem-1"],
        proposed_content=None,
        risk="low",
        reason="context expired",
        evidence_ids=["trace-1"],
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    applied = await reflection.apply_memory_maintenance_proposal(
        proposal.id,
        auto_policy=reflection.AutoMaintenancePolicy(allow_low_risk=True),
    )

    assert applied.status == "applied"
    mark_stale.assert_awaited_once_with("user-1", "mem-1")


@pytest.mark.parametrize("action", ["merge", "rewrite", "compact"])
async def test_medium_risk_actions_need_owner_approval(tmp_path, monkeypatch, action):
    from fleetent import reflection

    db_path = tmp_path / "maintenance.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    monkeypatch.setattr(reflection.memory, "update_user_memory_content", AsyncMock())
    monkeypatch.setattr(reflection.memory, "merge_user_memories", AsyncMock())
    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action=action,
        target_memory_ids=["mem-1", "mem-2"],
        proposed_content="User prefers Python.",
        risk="medium",
        reason="maintenance",
        evidence_ids=["trace-1"],
    )

    with pytest.raises(PermissionError, match="approval"):
        await reflection.apply_memory_maintenance_proposal(
            proposal.id,
            auto_policy=reflection.AutoMaintenancePolicy(allow_low_risk=True),
        )


async def test_suggest_shared_memory_or_kb_does_not_write_user_memory(tmp_path, monkeypatch):
    from fleetent import reflection

    db_path = tmp_path / "maintenance.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    update_memory = AsyncMock()
    monkeypatch.setattr(reflection.memory, "update_user_memory_content", update_memory)
    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="suggest_shared_memory_or_kb",
        target_memory_ids=[],
        proposed_content="Team uses GitHub Flow.",
        risk="low",
        reason="team convention",
        evidence_ids=["trace-1"],
    )
    reflection.approve_memory_maintenance_proposal(proposal.id, actor_user_id="user-1")

    applied = await reflection.apply_memory_maintenance_proposal(
        proposal.id,
        actor_user_id="user-1",
    )

    assert applied.status == "applied"
    update_memory.assert_not_awaited()


async def test_proposal_lifecycle_events_are_recorded(tmp_path, monkeypatch):
    from fleetent import observability, reflection

    db_path = tmp_path / "maintenance.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    monkeypatch.setattr(reflection.memory, "update_user_memory_content", AsyncMock())
    events: list[observability.TraceEvent] = []
    monkeypatch.setattr(observability, "record_trace_event", events.append)
    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="rewrite",
        target_memory_ids=["mem-1"],
        proposed_content="User prefers Python.",
        risk="medium",
        reason="clarify wording",
        evidence_ids=["trace-1"],
    )
    reflection.approve_memory_maintenance_proposal(proposal.id, actor_user_id="user-1")
    await reflection.apply_memory_maintenance_proposal(proposal.id, actor_user_id="user-1")

    assert [event.event_type for event in events] == [
        "memory_maintenance_proposal_created",
        "memory_maintenance_proposal_approved",
        "memory_maintenance_proposal_applied",
    ]
    assert {event.user_id for event in events} == {"user-1"}
    assert all(event.payload["proposal_id"] == proposal.id for event in events)


async def test_extract_ignores_unsupported_shared_memory_or_kb_actions(tmp_path, monkeypatch):
    from fleetent import memory as memory_layer

    db_path = tmp_path / "memory.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    monkeypatch.setattr(memory_store, "_state_db", SQLiteDatabase(path=db_path))
    monkeypatch.setattr(extraction.vector_store, "upsert", AsyncMock())
    _patch_extraction(
        monkeypatch,
        """
        [
          {
            "action": "create",
            "type": "preferences",
            "target": "shared_memory",
            "content": "Team uses GitHub Flow."
          },
          {
            "action": "create",
            "type": "context",
            "target": "knowledge_base",
            "content": "Project runbook lives in Confluence."
          }
        ]
        """,
    )

    await memory_layer.extract_and_update("user-1", [{"role": "user", "content": "facts"}])

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT content FROM memory_items").fetchall()

    assert rows == []
    extraction.vector_store.upsert.assert_not_awaited()


async def test_context_update_refreshes_ttl_and_rejects_cross_type_target(tmp_path, monkeypatch):
    from fleetent import memory as memory_layer

    db_path = tmp_path / "memory.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", _db_url(db_path))
    monkeypatch.setattr(memory_store, "_state_db", SQLiteDatabase(path=db_path))
    monkeypatch.setattr(extraction.vector_store, "upsert", AsyncMock())
    created_at = datetime(2026, 5, 1, tzinfo=UTC).isoformat()
    old_expiry = (datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "context-1",
                "user-1",
                "context",
                "User is working on billing",
                created_at,
                created_at,
                old_expiry,
            ),
        )
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "identity-1",
                "user-1",
                "identity",
                "User is an engineer",
                created_at,
                created_at,
                None,
            ),
        )
    before = datetime.now(UTC).replace(microsecond=0) + timedelta(days=30)
    _patch_extraction(
        monkeypatch,
        """
        [
          {
            "action": "update",
            "target_id": "context-1",
            "type": "context",
            "content": "User is working on billing migration"
          },
          {
            "action": "update",
            "target_id": "identity-1",
            "type": "context",
            "content": "Wrong cross-type update"
          }
        ]
        """,
    )

    await memory_layer.extract_and_update("user-1", [{"role": "user", "content": "facts"}])

    after = datetime.now(UTC).replace(microsecond=0) + timedelta(days=30)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        context = dict(
            conn.execute(
                "SELECT content, expires_at FROM memory_items WHERE id = ?", ("context-1",)
            ).fetchone()
        )
        identity = dict(
            conn.execute(
                "SELECT content, expires_at FROM memory_items WHERE id = ?", ("identity-1",)
            ).fetchone()
        )

    assert context["content"] == "User is working on billing migration"
    assert before <= datetime.fromisoformat(context["expires_at"]) <= after
    assert identity["content"] == "User is an engineer"
    assert identity["expires_at"] is None


def test_reflection_finding_filters_existing_and_single_evidence_memory_candidates():
    from fleetent import memory as memory_layer
    from fleetent import observability, reflection

    existing = [
        memory_layer.MemoryItem(
            id="mem-1",
            user_id="user-1",
            type="preferences",
            content="User prefers concise replies",
            created_at=datetime(2026, 6, 2, tzinfo=UTC),
            updated_at=datetime(2026, 6, 2, tzinfo=UTC),
            expires_at=None,
        )
    ]
    events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers concise replies"},
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"memory_fact": "User likes incident reviews"},
        ),
        observability.TraceEvent(
            id="trace-3",
            run_id="run-3",
            event_type="agent_run_completed",
            payload={"memory_fact": "User likes incident reviews"},
        ),
        observability.TraceEvent(
            id="trace-4",
            run_id="run-4",
            event_type="agent_run_completed",
            payload={"memory_fact": "User has one-off request"},
        ),
    ]

    findings = reflection._generate_findings(events, existing)

    assert [finding.metadata["fact"] for finding in findings] == ["User likes incident reviews"]


def _patch_extraction(monkeypatch, content: str) -> AsyncMock:

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace()))
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )
    )
    client.chat.completions.create = create
    monkeypatch.setattr(extraction, "AsyncOpenAI", lambda **kwargs: client)
    return create
