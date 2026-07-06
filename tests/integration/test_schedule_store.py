"""Tests for schedule_store: create, list_tasks, delete."""

import fleetent.schedule_store as ss


def test_schedule_store_does_not_expose_legacy_db_path():
    assert not hasattr(ss, "DB_PATH")


def test_create_returns_dict_with_uuid_id(isolated_schedule_db):
    task = ss.create(
        name="daily",
        cron_expr="0 9 * * 1-5",
        timezone="UTC",
        user_id="u-1",
        message="run report",
        source="dynamic",
    )
    assert isinstance(task["id"], str) and len(task["id"]) == 36  # UUID
    assert task["name"] == "daily"
    assert task["cron_expr"] == "0 9 * * 1-5"
    assert task["user_id"] == "u-1"
    assert task["message"] == "run report"
    assert task["source"] == "dynamic"
    assert task["enabled"] == 1


def test_list_tasks_returns_all_rows(isolated_schedule_db):
    ss.create("a", "* * * * *", "UTC", "u-1", "msg-a", "dynamic")
    ss.create("b", "0 0 * * *", "UTC", "u-2", "msg-b", "static")
    tasks = ss.list_tasks()
    assert len(tasks) == 2
    names = {t["name"] for t in tasks}
    assert names == {"a", "b"}


def test_delete_removes_task(isolated_schedule_db):
    task = ss.create("x", "* * * * *", "UTC", "u-1", "msg", "dynamic")
    deleted = ss.delete(task["id"])
    assert deleted is True
    assert ss.list_tasks() == []


def test_delete_nonexistent_returns_false(isolated_schedule_db):
    result = ss.delete("00000000-0000-0000-0000-000000000000")
    assert result is False


def test_list_tasks_empty_db(isolated_schedule_db):
    assert ss.list_tasks() == []


def test_update_run_state_writing_status_preserves_next_run_at(isolated_schedule_db):
    """update_run_state is field-selective (PATCH): writing status columns must not
    clear next_run_at (fix-cron-store-and-once F1 — AAA-8288)."""
    task = ss.create("a", "* * * * *", "UTC", "u-1", "msg", "dynamic")
    ss.update_run_state(task["id"], next_run_at="2026-07-01T12:00:00+00:00")

    ss.update_run_state(task["id"], last_run_at="2026-07-01T12:00:01Z", last_status="ok")

    row = ss.get(task["id"])
    assert row["next_run_at"] == "2026-07-01T12:00:00+00:00"
    assert row["last_status"] == "ok"
    assert row["last_run_at"] == "2026-07-01T12:00:01Z"


def test_update_run_state_writing_next_run_at_preserves_status(isolated_schedule_db):
    """The reverse direction: advancing next_run_at must not clear a previously
    recorded status/error."""
    task = ss.create("a", "* * * * *", "UTC", "u-1", "msg", "dynamic")
    ss.update_run_state(
        task["id"], last_run_at="2026-07-01T12:00:00Z", last_status="error", last_error="boom"
    )

    ss.update_run_state(task["id"], next_run_at="2026-07-01T12:01:00+00:00")

    row = ss.get(task["id"])
    assert row["next_run_at"] == "2026-07-01T12:01:00+00:00"
    assert row["last_status"] == "error"
    assert row["last_error"] == "boom"
    assert row["last_run_at"] == "2026-07-01T12:00:00Z"
