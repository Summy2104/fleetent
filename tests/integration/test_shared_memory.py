import sqlite3

import pytest

from fleetent.db import create_database


def _patch_db(monkeypatch, tmp_path):
    from fleetent import reflection
    from fleetent.memory import store
    from tests.integration.test_migrations import apply_migrations

    db_path = tmp_path / "shared-memory-apply.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(store, "database", lambda: database)
    monkeypatch.setattr(reflection, "_database", lambda: database)
    monkeypatch.setattr(reflection.observability, "record_trace_event", lambda event: None)
    return db_path


async def test_approved_shared_memory_proposal_apply_creates_item(monkeypatch, tmp_path):
    db_path = _patch_db(monkeypatch, tmp_path)
    from fleetent import memory, reflection
    from fleetent.memory import shared

    upserts: list[tuple[str, str, str]] = []

    async def upsert(id: str, text: str, namespace: str) -> None:
        upserts.append((id, text, namespace))

    monkeypatch.setattr(shared.vector_store, "upsert", upsert)

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="owner",
        action="suggest_shared_memory_or_kb",
        target_memory_ids=[],
        proposed_content="Team uses GitHub Flow for releases.",
        risk="medium",
        reason="Repeated team convention is not user memory.",
        evidence_ids=["trace-1", "trace-2"],
        metadata_patch={
            "target": "shared_memory",
            "scope_type": "team",
            "scope_id": "eng",
            "type": "procedure",
        },
    )
    reflection.approve_memory_maintenance_proposal(proposal.id, actor_user_id="owner")

    item = await memory.apply_shared_memory_proposal(proposal.id, actor_id="owner")

    assert item.scope_type == "team"
    assert item.scope_id == "eng"
    assert item.type == "procedure"
    assert item.source == "reflection_proposal"
    assert item.source_ref == proposal.id
    assert upserts == [(item.id, item.content, "shared:team:eng")]
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM memory_maintenance_proposals WHERE id = ?",
            (proposal.id,),
        ).fetchone()
    assert row == ("applied",)


async def test_shared_memory_proposal_apply_allows_non_owner_admin_actor(monkeypatch, tmp_path):
    db_path = _patch_db(monkeypatch, tmp_path)
    from fleetent import memory, reflection
    from fleetent.memory import shared

    upserts: list[tuple[str, str, str]] = []

    async def upsert(id: str, text: str, namespace: str) -> None:
        upserts.append((id, text, namespace))

    monkeypatch.setattr(shared.vector_store, "upsert", upsert)

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="memory-owner",
        action="suggest_shared_memory_or_kb",
        target_memory_ids=[],
        proposed_content="Tenant support uses the enterprise escalation playbook.",
        risk="medium",
        reason="Shared tenant procedure is not user memory.",
        evidence_ids=["trace-1", "trace-2"],
        metadata_patch={
            "target": "shared_memory",
            "scope_type": "tenant",
            "scope_id": "acme",
            "type": "procedure",
        },
    )
    reflection.approve_memory_maintenance_proposal(proposal.id, actor_user_id="memory-owner")

    item = await memory.apply_shared_memory_proposal(proposal.id, actor_id="tenant-admin")

    assert item.created_by == "tenant-admin"
    assert upserts == [(item.id, item.content, "shared:tenant:acme")]
    with sqlite3.connect(db_path) as conn:
        proposal_row = conn.execute(
            "SELECT status FROM memory_maintenance_proposals WHERE id = ?",
            (proposal.id,),
        ).fetchone()
        shared_rows = conn.execute(
            "SELECT id, source_ref FROM shared_memory_items WHERE source_ref = ?",
            (proposal.id,),
        ).fetchall()
    assert proposal_row == ("applied",)
    assert shared_rows == [(item.id, proposal.id)]


@pytest.mark.parametrize(
    "metadata_patch",
    [
        {"target": "knowledge_base", "scope_type": "team", "scope_id": "eng", "type": "context"},
        {"target": "shared_memory", "scope_type": "user", "scope_id": "u1", "type": "context"},
    ],
)
async def test_shared_memory_proposal_apply_rejects_invalid_target_or_scope(
    monkeypatch, tmp_path, metadata_patch
):
    _patch_db(monkeypatch, tmp_path)
    from fleetent import memory, reflection

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="owner",
        action="suggest_shared_memory_or_kb",
        target_memory_ids=[],
        proposed_content="Team context.",
        risk="medium",
        reason="Needs shared memory review.",
        evidence_ids=["trace-1"],
        metadata_patch=metadata_patch,
    )
    reflection.approve_memory_maintenance_proposal(proposal.id, actor_user_id="owner")

    with pytest.raises(ValueError):
        await memory.apply_shared_memory_proposal(proposal.id, actor_id="owner")


async def test_shared_memory_proposal_apply_requires_approved_status(monkeypatch, tmp_path):
    _patch_db(monkeypatch, tmp_path)
    from fleetent import memory, reflection

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="owner",
        action="suggest_shared_memory_or_kb",
        target_memory_ids=[],
        proposed_content="Team context.",
        risk="medium",
        reason="Needs shared memory review.",
        evidence_ids=["trace-1"],
        metadata_patch={
            "target": "shared_memory",
            "scope_type": "team",
            "scope_id": "eng",
            "type": "context",
        },
    )

    with pytest.raises(ValueError, match="pending"):
        await memory.apply_shared_memory_proposal(proposal.id, actor_id="owner")
