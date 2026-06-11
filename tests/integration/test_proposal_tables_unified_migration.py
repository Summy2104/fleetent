"""agent-runtime-db-routing-cleanup: memory_maintenance_proposals and skill_proposals
are created by the unified AGENT_STATE_MIGRATIONS on the per-agent agent_state.db, so the
memory/proposal_store and reflection stores read/write them without any independent
ensure_schema bypass and without touching a management DB."""

from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


def _boot_agent_state(tmp_path, agent_id="agent"):
    """Open a migrated per-agent agent_state.db and inject it into the agent-side stores."""
    from fleetent import reflection
    from fleetent.memory import store as memory_store
    from fleetent.observability import traces

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", agent_id).open_state_db(MIGRATIONS)
    reflection.set_state_db(db)
    memory_store.set_state_db(db)
    traces.set_state_db(db)
    return db


def test_memory_maintenance_proposal_roundtrips_via_unified_migration(tmp_path):
    from fleetent import reflection
    from fleetent.memory import proposal_store

    _boot_agent_state(tmp_path)

    created = reflection.create_memory_maintenance_proposal(
        user_id="u1",
        action="mark_stale",
        target_memory_ids=["m1"],
        proposed_content=None,
        risk="low",
        reason="stale fact",
        evidence_ids=["trace-a"],
    )

    # proposal_store reads through memory.store.database() (the same agent_state.db):
    # the table exists purely because of the unified MIGRATIONS, no Alembic / ensure_schema.
    loaded = proposal_store.get_memory_maintenance_proposal(created.id)
    assert loaded.id == created.id
    assert loaded.user_id == "u1"
    assert loaded.status == "pending"

    listed = proposal_store.list_memory_maintenance_proposals("u1")
    assert [p.id for p in listed] == [created.id]


def test_skill_proposal_roundtrips_via_unified_migration(tmp_path):
    from fleetent import reflection
    from fleetent.reflection import ReflectionFinding

    _boot_agent_state(tmp_path)

    [proposal] = reflection.generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: triage incidents",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "triage incidents"},
            )
        ]
    )

    listed = reflection.list_skill_proposals("pending")
    assert any(p.id == proposal.id for p in listed)
    assert reflection.get_skill_proposal(proposal.id).status == "pending"
