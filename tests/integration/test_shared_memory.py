"""Integration tests for shared memory apply-proposal flow.

Updated for shared-memory-lib (3c): patches inject set_shared_memory_db
for the shared memory DB; reflection proposals now live in agent_state.db.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fleetent.db import SQLiteDatabase, create_database
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _patch_db(monkeypatch: Any, tmp_path: Path) -> tuple[Path, list[tuple[str, str, str]]]:
    """Set up the test DB fixtures and inject shared memory state.

    Returns:
        Tuple of (agent_state_db_path, upsert_calls) where upsert_calls accumulates
        (id, content_or_any, namespace) from the shared memory vector backend.
    """
    from fleetent import reflection
    from fleetent.memory import shared, store
    from fleetent.memory.shared_memory_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    # Agent-side state DB for reflection proposals + memory store
    db_path = tmp_path / "shared-memory-apply.db"
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(store, "database", lambda: database)
    monkeypatch.setattr(reflection, "_state_db", SQLiteDatabase(path=db_path))
    monkeypatch.setattr(reflection.observability, "record_trace_event", lambda event: None)

    # Per-tenant shared_memory.db for shared memory items
    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    sm_db = scope.open_shared_memory_db(MIGRATIONS)

    upsert_calls: list[tuple[str, str, str]] = []

    class _TrackingBackend:
        async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
            upsert_calls.append((id, "", namespace))  # content embedded → not captured

        async def search(self, vector: list[float], namespace: str, limit: int = 10) -> list[Any]:
            return []

        async def delete(self, id: str, namespace: str) -> None:
            pass

        async def clear_namespace(self, namespace: str) -> None:
            pass

    monkeypatch.setattr(shared, "_shared_memory_db", sm_db)
    monkeypatch.setattr(shared, "_shared_memory_vector_backend", _TrackingBackend())

    return db_path, upsert_calls


async def test_approved_shared_memory_proposal_apply_creates_item(
    monkeypatch: Any, tmp_path: Path
) -> None:
    db_path, upsert_calls = _patch_db(monkeypatch, tmp_path)
    from fleetent import memory, reflection

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
    # vector backend received upsert with correct namespace
    assert any(id_ == item.id and ns == "shared:team:eng" for id_, _, ns in upsert_calls)
    # proposal projection now derives lifecycle from approval_requests + applied_at
    assert reflection.get_memory_maintenance_proposal(proposal.id).status == "applied"


async def test_shared_memory_proposal_apply_allows_non_owner_admin_actor(
    monkeypatch: Any, tmp_path: Path
) -> None:
    db_path, upsert_calls = _patch_db(monkeypatch, tmp_path)
    from fleetent import memory, reflection

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
    assert any(id_ == item.id and ns == "shared:tenant:acme" for id_, _, ns in upsert_calls)
    assert reflection.get_memory_maintenance_proposal(proposal.id).status == "applied"


@pytest.mark.parametrize(
    "metadata_patch",
    [
        {"target": "knowledge_base", "scope_type": "team", "scope_id": "eng", "type": "context"},
        {"target": "shared_memory", "scope_type": "user", "scope_id": "u1", "type": "context"},
    ],
)
async def test_shared_memory_proposal_apply_rejects_invalid_target_or_scope(
    monkeypatch: Any, tmp_path: Path, metadata_patch: dict[str, str]
) -> None:
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


async def test_shared_memory_proposal_apply_requires_approved_status(
    monkeypatch: Any, tmp_path: Path
) -> None:
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
