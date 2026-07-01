"""Tests for the scheduled_task_runs history table and schedule_store run APIs."""

import fleetent.schedule_store as ss


def _table_names(state_db) -> set[str]:
    rows = state_db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r["name"] for r in rows}


def test_migration_creates_scheduled_task_runs_table(isolated_schedule_db):
    # 1.1: after agent_state migrations, the run-history table exists with the expected columns.
    assert "scheduled_task_runs" in _table_names(isolated_schedule_db)
    cols = {
        r["name"]
        for r in isolated_schedule_db.execute("PRAGMA table_info(scheduled_task_runs)").fetchall()
    }
    assert {
        "task_id",
        "fired_at",
        "status",
        "agent_error",
        "delivery_error",
        "duration_ms",
        "kind",
    } <= cols


def test_record_run_and_list_runs_recent_first(isolated_schedule_db):
    task = ss.create("t", "* * * * *", "UTC", "u-1", "msg", "dynamic")
    ss.record_run(task["id"], status="ok", fired_at="2026-07-01T00:00:00Z", kind="generate")
    ss.record_run(
        task["id"],
        status="error",
        fired_at="2026-07-01T00:01:00Z",
        kind="generate",
        agent_error=None,
        delivery_error="slack down",
        duration_ms=1234,
    )
    runs = ss.list_runs(task["id"], limit=10)
    assert len(runs) == 2
    # most recent first
    assert runs[0]["fired_at"] == "2026-07-01T00:01:00Z"
    assert runs[0]["status"] == "error"
    assert runs[0]["delivery_error"] == "slack down"
    assert runs[0]["agent_error"] is None
    assert runs[0]["duration_ms"] == 1234
    assert runs[1]["fired_at"] == "2026-07-01T00:00:00Z"


def test_record_run_prunes_beyond_retention(isolated_schedule_db):
    task = ss.create("t", "* * * * *", "UTC", "u-1", "msg", "dynamic")
    for i in range(7):
        ss.record_run(
            task["id"],
            status="ok",
            fired_at=f"2026-07-01T00:0{i}:00Z",
            kind="generate",
            retention=3,
        )
    runs = ss.list_runs(task["id"], limit=100)
    assert len(runs) == 3
    # only the newest 3 survive
    assert [r["fired_at"] for r in runs] == [
        "2026-07-01T00:06:00Z",
        "2026-07-01T00:05:00Z",
        "2026-07-01T00:04:00Z",
    ]


def test_delete_task_cascades_run_history(isolated_schedule_db):
    task = ss.create("t", "* * * * *", "UTC", "u-1", "msg", "dynamic")
    ss.record_run(task["id"], status="ok", fired_at="2026-07-01T00:00:00Z", kind="generate")
    assert ss.list_runs(task["id"], limit=10)
    ss.delete(task["id"])
    assert ss.list_runs(task["id"], limit=10) == []


def test_list_runs_unknown_task_empty(isolated_schedule_db):
    assert ss.list_runs("does-not-exist", limit=10) == []
