"""Tests for CronScheduler and _fire dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock

# ── CronScheduler lifecycle ──────────────────────────────────────────────────


async def test_start_makes_scheduler_running(tmp_path, monkeypatch, isolated_schedule_db):
    import fleetent.cron_scheduler as cs

    scheduler = cs.CronScheduler()
    await scheduler.start()
    assert scheduler.running
    await scheduler.shutdown()


async def test_add_job_registers_in_scheduler(tmp_path, monkeypatch, isolated_schedule_db):
    import fleetent.cron_scheduler as cs

    scheduler = cs.CronScheduler()
    await scheduler.start()

    task = {
        "id": "job-1",
        "name": "t",
        "cron_expr": "0 9 * * *",
        "timezone": "UTC",
        "user_id": "u-1",
        "agent_name": None,
        "message": "hi",
        "enabled": 1,
        "source": "dynamic",
    }
    scheduler.add_job(task)
    assert scheduler.get_job("job-1") is not None

    await scheduler.shutdown()


async def test_remove_job_deletes_from_scheduler(tmp_path, monkeypatch, isolated_schedule_db):
    import fleetent.cron_scheduler as cs

    scheduler = cs.CronScheduler()
    await scheduler.start()

    task = {
        "id": "job-2",
        "name": "t",
        "cron_expr": "0 9 * * *",
        "timezone": "UTC",
        "user_id": "u-1",
        "agent_name": None,
        "message": "hi",
        "enabled": 1,
        "source": "dynamic",
    }
    scheduler.add_job(task)
    scheduler.remove_job("job-2")
    assert scheduler.get_job("job-2") is None

    await scheduler.shutdown()


async def test_shutdown_stops_scheduler(tmp_path, monkeypatch, isolated_schedule_db):
    import fleetent.cron_scheduler as cs

    scheduler = cs.CronScheduler()
    await scheduler.start()
    await scheduler.shutdown()
    assert not scheduler.running


# ── _fire dispatches agent_loop.run() ────────────────────────────────────────


async def test_fire_calls_agent_loop_run(tmp_path, monkeypatch):
    import fleetent.cron_scheduler as cs
    import fleetent.session.manager as session_mgr

    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    run_mock = AsyncMock(return_value="reply")
    monkeypatch.setattr(cs, "_agent_run", run_mock)

    task = {
        "id": "t1",
        "name": "n",
        "cron_expr": "* * * * *",
        "timezone": "UTC",
        "user_id": "fire-user",
        "agent_name": "bot",
        "message": "hello from cron",
        "enabled": 1,
        "source": "dynamic",
    }

    await cs._fire(task)

    run_mock.assert_called_once()
    call_kwargs = run_mock.call_args[1]
    assert call_kwargs["user_id"] == "fire-user"
    assert call_kwargs.get("agent_name") == "bot"


async def test_fire_message_in_user_content(tmp_path, monkeypatch):
    import fleetent.cron_scheduler as cs
    import fleetent.session.manager as session_mgr

    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    run_mock = AsyncMock(return_value="ok")
    monkeypatch.setattr(cs, "_agent_run", run_mock)

    task = {
        "id": "t2",
        "name": "n",
        "cron_expr": "* * * * *",
        "timezone": "UTC",
        "user_id": "u-1",
        "agent_name": None,
        "message": "generate report",
        "enabled": 1,
        "source": "dynamic",
    }

    await cs._fire(task)

    messages = run_mock.call_args[0][0]
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assert any("generate report" in m["content"] for m in user_msgs)


# ── settings-backed startup ───────────────────────────────────────────────────


async def test_start_fails_fast_when_legacy_cron_yaml_exists(
    tmp_path, monkeypatch, isolated_schedule_db
):
    import pytest

    import fleetent.cron_scheduler as cs

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "cron.yaml").write_text("jobs: []\n")
    monkeypatch.chdir(tmp_path)

    scheduler = cs.CronScheduler()
    with pytest.raises(RuntimeError, match="SQLite-backed runtime management"):
        await scheduler.start()


def test_cron_yaml_loader_is_removed():
    import fleetent.cron_scheduler as cs

    assert not hasattr(cs, "load_cron_yaml")


async def test_start_respects_disabled_scheduling_setting(isolated_schedule_db):
    import fleetent.cron_scheduler as cs
    from fleetent.config import SchedulingSettings

    scheduler = cs.CronScheduler(settings=SchedulingSettings(enabled=False))

    await scheduler.start()

    assert not scheduler.running


async def test_start_uses_default_timezone_when_task_has_none(monkeypatch, isolated_schedule_db):
    import fleetent.cron_scheduler as cs
    from fleetent.config import SchedulingSettings

    monkeypatch.setattr(
        cs._store,
        "list_tasks",
        lambda: [
            {
                "id": "job-default-tz",
                "name": "t",
                "cron_expr": "0 9 * * *",
                "timezone": None,
                "user_id": "u-1",
                "agent_name": None,
                "message": "hi",
                "enabled": 1,
                "source": "dynamic",
            }
        ],
    )
    scheduler = cs.CronScheduler(settings=SchedulingSettings(default_timezone="Asia/Shanghai"))

    await scheduler.start()

    job = scheduler.get_job("job-default-tz")
    assert job is not None
    assert str(job.trigger.timezone) == "Asia/Shanghai"

    await scheduler.shutdown()
