"""agent-runtime-db-routing-cleanup: session_anti_flap and sub_agent_runs are reached
through the per-agent state DB (agent_scope + db.py), so under platform multi-agent each
agent's records land in its own agent_state.db and never in the shared management DB."""

import sqlite3

from fleetent.runtime import context as runtime_context
from fleetent.runtime import sub_agent_lifecycle as sal
from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.runtime.context import AntiFlapState
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


def _open_agent_state(data_dir, agent_id):
    router = TenantRouter(SQLiteTenantBackend(data_dir=data_dir))
    return router.agent_scope("default", agent_id).open_state_db(MIGRATIONS)


def _bind(state_db):
    runtime_context.set_state_db(state_db)
    sal.set_state_db(state_db)


def _table_rows(db_path, table, where_col, where_val):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return conn.execute(f"SELECT * FROM {table} WHERE {where_col} = ?", (where_val,)).fetchall()
    finally:
        conn.close()


def test_anti_flap_and_sub_agent_records_land_in_per_agent_state_db(tmp_path):
    data_dir = tmp_path / "data"
    db_a = _open_agent_state(data_dir, "agent-a")
    db_b = _open_agent_state(data_dir, "agent-b")

    # Agent A writes its own anti-flap state + sub-agent run.
    _bind(db_a)
    runtime_context.save_anti_flap_state(
        "sess-a",
        AntiFlapState(recent_savings=(0.1,), turns_since_last_compress=2, auto_disabled=True),
    )
    sal.upsert(
        sal.SubAgentLifecycle(
            run_id="run-a",
            parent_session_id="sess-a",
            name="task-a",
            timeout_seconds=300,
            created_at="2026-06-01T00:00:00Z",
        )
    )

    # Agent B writes different records through the same module-level API.
    _bind(db_b)
    runtime_context.save_anti_flap_state(
        "sess-b",
        AntiFlapState(recent_savings=(0.9,), turns_since_last_compress=0, auto_disabled=False),
    )
    sal.upsert(
        sal.SubAgentLifecycle(
            run_id="run-b",
            parent_session_id="sess-b",
            name="task-b",
            timeout_seconds=300,
            created_at="2026-06-01T00:00:00Z",
        )
    )

    # Physical isolation: each record is in its owner's file only.
    assert len(_table_rows(db_a.path, "session_anti_flap", "session_id", "sess-a")) == 1
    assert len(_table_rows(db_a.path, "session_anti_flap", "session_id", "sess-b")) == 0
    assert len(_table_rows(db_b.path, "session_anti_flap", "session_id", "sess-b")) == 1
    assert len(_table_rows(db_b.path, "session_anti_flap", "session_id", "sess-a")) == 0

    assert len(_table_rows(db_a.path, "sub_agent_runs", "parent_session_id", "sess-a")) == 1
    assert len(_table_rows(db_b.path, "sub_agent_runs", "parent_session_id", "sess-b")) == 1
    assert len(_table_rows(db_a.path, "sub_agent_runs", "parent_session_id", "sess-b")) == 0

    # The two agent state files are distinct, and no shared management DB exists at the root.
    assert db_a.path != db_b.path
    assert not (data_dir / "management.db").exists()
    assert not (data_dir / "fleetent.db").exists()


def test_anti_flap_roundtrip_through_state_db(tmp_path):
    _bind(_open_agent_state(tmp_path / "data", "agent-x"))
    runtime_context.save_anti_flap_state(
        "sess-x",
        AntiFlapState(recent_savings=(0.05, 0.2), turns_since_last_compress=3, auto_disabled=True),
    )
    loaded = runtime_context.load_anti_flap_state("sess-x")
    assert loaded.recent_savings == (0.05, 0.2)
    assert loaded.turns_since_last_compress == 3
    assert loaded.auto_disabled is True
    assert runtime_context.load_anti_flap_state("never-seen") == AntiFlapState()
