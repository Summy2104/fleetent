"""agent-runtime-db-routing-cleanup baseline: with no platform and no management-DB tables,
agent boot creates the four runtime tables in the agent's own agent_state.db, and the
agent-side stores persist there — never in the (absent) shared management library."""

import sqlite3

import pytest


@pytest.fixture
def _restore_runtime_state_dbs():
    """Restore the process-global state-db handles boot() mutates (context / sub_agent /
    memory_store); the conftest only resets traces + reflection."""
    from fleetent.memory import store as memory_store
    from fleetent.runtime import context as runtime_context
    from fleetent.runtime import sub_agent_lifecycle

    saved = (runtime_context._state_db, sub_agent_lifecycle._state_db, memory_store._state_db)
    yield
    runtime_context._state_db, sub_agent_lifecycle._state_db, memory_store._state_db = saved


_RUNTIME_TABLES = (
    "session_anti_flap",
    "sub_agent_runs",
    "memory_maintenance_proposals",
    "skill_proposals",
)


def _tables(db_path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_standalone_boot_lands_runtime_tables_in_agent_state_db(
    tmp_path, monkeypatch, _restore_runtime_state_dbs
):
    from fleetent import reflection
    from fleetent.memory import store as memory_store
    from fleetent.runtime import agent_app, sub_agent_lifecycle
    from fleetent.runtime import context as runtime_context
    from fleetent.runtime.sub_agent_lifecycle import SubAgentLifecycle

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    mgmt_db = data_dir / "management.db"  # deliberately never migrated: no platform, no tables
    db_url = f"sqlite:///{mgmt_db}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    # Boot the agent's DB schema exactly as `fleetent agent run` does, without any platform.
    agent_app._init_agent_db_schema(db_url, agent_id="solo-bot", tenant_id="default")

    agent_state_db = data_dir / "default" / "solo-bot" / "agent_state.db"
    assert agent_state_db.exists()
    tables = _tables(agent_state_db)
    for table in _RUNTIME_TABLES:
        assert table in tables, f"{table} missing from agent_state.db after boot"

    # The agent-side stores now write through the injected agent_state.db handle.
    runtime_context.save_anti_flap_state(
        "sess-1", runtime_context.AntiFlapState(turns_since_last_compress=4)
    )
    sub_agent_lifecycle.upsert(
        SubAgentLifecycle(
            run_id="run-1",
            parent_session_id="sess-1",
            name="task",
            timeout_seconds=300,
            created_at="2026-06-01T00:00:00Z",
        )
    )
    monkeypatch.setattr(reflection.observability, "record_trace_event", lambda event: None)
    proposal = reflection.create_memory_maintenance_proposal(
        user_id="u1",
        action="mark_stale",
        target_memory_ids=["m1"],
        proposed_content=None,
        risk="low",
        reason="stale",
        evidence_ids=["t1"],
    )

    # Rows land in the per-agent agent_state.db...
    conn = sqlite3.connect(agent_state_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM session_anti_flap").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM sub_agent_runs").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM memory_maintenance_proposals").fetchone()[0] == 1
    finally:
        conn.close()
    # ...and proposal_store reads them back from that same physical file.
    from fleetent.memory import proposal_store

    assert memory_store.database().path == agent_state_db
    assert proposal_store.get_memory_maintenance_proposal(proposal.id).id == proposal.id

    # The management DB was never created with these agent tables (no platform involved).
    if mgmt_db.exists():
        assert _tables(mgmt_db).isdisjoint(set(_RUNTIME_TABLES))
