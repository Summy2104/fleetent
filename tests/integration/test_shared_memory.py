import sqlite3

import pytest

from fleetent.db import create_database


def _patch_db(monkeypatch, tmp_path):
    from fleetent.intelligence import reflection
    from fleetent.intelligence.memory import store
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
    from fleetent.intelligence import memory, reflection
    from fleetent.intelligence.memory import shared

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
    from fleetent.intelligence import memory, reflection

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
    from fleetent.intelligence import memory, reflection

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
