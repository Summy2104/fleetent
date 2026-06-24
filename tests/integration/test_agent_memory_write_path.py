"""Integration: approve a target=agent_memory proposal truly writes to agent_memory_items."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fleetent import vector_store
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter
from fleetent.vector_store.backend import SQLiteVectorBackend


def _boot_agent_state(tmp_path, monkeypatch, agent_id="agent"):
    """Wire all agent-side stores to a fresh migrated state_db; use monkeypatch for cleanup."""
    from fleetent import reflection
    from fleetent.governance import approval_request_store
    from fleetent.memory import store as memory_store
    from fleetent.observability import traces

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", agent_id).open_state_db(AGENT_STATE_MIGRATIONS)

    monkeypatch.setattr(reflection, "_state_db", db)
    monkeypatch.setattr(approval_request_store, "_state_db", db)
    monkeypatch.setattr(memory_store, "_state_db", db)
    monkeypatch.setattr(traces, "_state_db", db)
    return db


async def test_approve_agent_memory_proposal_creates_memory_item_and_marks_applied(
    tmp_path, monkeypatch
):
    """Resolving an agent_memory proposal must write agent_memory_items row and mark status=applied."""
    db = _boot_agent_state(tmp_path, monkeypatch)

    from fleetent.memory import agent_memory

    vector_backend = SQLiteVectorBackend(
        database_url=f"sqlite:///{tmp_path / 'agent_memory_vectors.db'}"
    )
    monkeypatch.setattr(agent_memory, "_agent_memory_db", db)
    monkeypatch.setattr(agent_memory, "_agent_memory_vector_backend", vector_backend)
    monkeypatch.setattr(vector_store, "embed_text", AsyncMock(return_value=[0.1, 0.2, 0.3]))

    from fleetent import reflection as reflection_api

    proposed_content = "User prefers bullet points for complex explanations"
    proposal = reflection_api.create_memory_maintenance_proposal(
        user_id="user-1",
        action="suggest_agent_memory_or_kb",
        target_memory_ids=[],
        proposed_content=proposed_content,
        metadata_patch={"target": "agent_memory", "type": "preference"},
        risk="low",
        reason="recurring formatting preference detected across sessions",
        evidence_ids=["trace-1"],
    )
    proposal_id = proposal.id

    from fleetent.governance.reflection_gate import resolve_reflection_proposal_action

    await resolve_reflection_proposal_action(
        proposal_id,
        decision="approve",
        actor_user_id="user-1",
    )

    # proposal must be marked applied
    from fleetent.memory.proposal_store import get_memory_maintenance_proposal

    reloaded = get_memory_maintenance_proposal(proposal_id)
    assert reloaded.status == "applied", f"expected applied, got {reloaded.status!r}"

    # agent_memory_items must have the row with correct fields
    items = agent_memory.list_agent_memory()
    assert len(items) == 1
    assert items[0].content == proposed_content
    assert items[0].source == "reflection_proposal"
    assert items[0].source_ref == proposal_id

    # vector search must find the item
    results = await agent_memory.search_agent_memory("bullet points explanations")
    assert len(results) >= 1
    assert results[0].id == items[0].id
