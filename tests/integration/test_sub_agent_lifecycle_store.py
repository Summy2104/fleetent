"""DB-backed sub-agent lifecycle persistence tests.

The sub_agent_runs schema is created by the unified AGENT_STATE_MIGRATIONS on the
per-agent agent_state.db; tests inject that migrated handle rather than monkeypatching
a global DB_PATH (agent-runtime-db-routing-cleanup)."""


def _bind_state_db(sal, tmp_path, agent_id="agent"):
    from fleetent.runtime.agent_state_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", agent_id).open_state_db(MIGRATIONS)
    sal.set_state_db(db)
    return db


def _lc(run_id, parent, name="t", state=None):
    from fleetent.runtime.sub_agent_lifecycle import SubAgentLifecycle, SubAgentState

    return SubAgentLifecycle(
        run_id=run_id,
        parent_session_id=parent,
        name=name,
        state=state or SubAgentState.pending,
        timeout_seconds=300,
        created_at="2026-06-01T00:00:00Z",
    )


def test_migrate_on_open_is_idempotent(tmp_path):
    import fleetent.runtime.sub_agent_lifecycle as sal

    _bind_state_db(sal, tmp_path)
    sal.upsert(_lc("r1", "s1"))
    _bind_state_db(sal, tmp_path)  # re-open + migrate must not drop data
    rows = sal.query_by_parent("s1")
    assert len(rows) == 1


def test_upsert_then_read_back(tmp_path):
    import fleetent.runtime.sub_agent_lifecycle as sal

    _bind_state_db(sal, tmp_path)
    sal.upsert(_lc("r1", "s1", name="alpha"))
    rows = sal.query_by_parent("s1")
    assert rows[0].run_id == "r1"
    assert rows[0].name == "alpha"
    assert rows[0].state is sal.SubAgentState.pending


def test_query_reflects_terminal_state_and_ended_at(tmp_path):
    import fleetent.runtime.sub_agent_lifecycle as sal

    _bind_state_db(sal, tmp_path)
    lc = _lc("r1", "s1")
    sal.upsert(lc)
    lc.state = sal.SubAgentState.succeeded
    lc.started_at = "2026-06-01T00:00:01Z"
    lc.ended_at = "2026-06-01T00:00:05Z"
    sal.upsert(lc)
    row = sal.query_by_parent("s1")[0]
    assert row.state is sal.SubAgentState.succeeded
    assert row.ended_at == "2026-06-01T00:00:05Z"


def test_query_by_parent_filters(tmp_path):
    import fleetent.runtime.sub_agent_lifecycle as sal

    _bind_state_db(sal, tmp_path)
    sal.upsert(_lc("r1", "s1"))
    sal.upsert(_lc("r2", "s1"))
    sal.upsert(_lc("r3", "s2"))
    assert {r.run_id for r in sal.query_by_parent("s1")} == {"r1", "r2"}
    assert {r.run_id for r in sal.query_by_parent("s2")} == {"r3"}
