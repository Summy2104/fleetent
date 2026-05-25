"""Tests for schedule_store: create, list_tasks, delete."""

import mini_agent.schedule_store as ss


def test_create_returns_dict_with_uuid_id(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "DB_PATH", tmp_path / "test.db")
    task = ss.create(
        name="daily",
        cron_expr="0 9 * * 1-5",
        timezone="UTC",
        user_id="u-1",
        agent_name=None,
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


def test_list_tasks_returns_all_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "DB_PATH", tmp_path / "test.db")
    ss.create("a", "* * * * *", "UTC", "u-1", None, "msg-a", "dynamic")
    ss.create("b", "0 0 * * *", "UTC", "u-2", "bot", "msg-b", "static")
    tasks = ss.list_tasks()
    assert len(tasks) == 2
    names = {t["name"] for t in tasks}
    assert names == {"a", "b"}


def test_delete_removes_task(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "DB_PATH", tmp_path / "test.db")
    task = ss.create("x", "* * * * *", "UTC", "u-1", None, "msg", "dynamic")
    deleted = ss.delete(task["id"])
    assert deleted is True
    assert ss.list_tasks() == []


def test_delete_nonexistent_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "DB_PATH", tmp_path / "test.db")
    result = ss.delete("00000000-0000-0000-0000-000000000000")
    assert result is False


def test_list_tasks_empty_db(tmp_path, monkeypatch):
    monkeypatch.setattr(ss, "DB_PATH", tmp_path / "test.db")
    assert ss.list_tasks() == []
