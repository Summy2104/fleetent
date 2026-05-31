"""Tests for CronScheduler and _fire dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock

# ── CronScheduler lifecycle ──────────────────────────────────────────────────


async def test_start_makes_scheduler_running(tmp_path, monkeypatch, isolated_schedule_db):
    import fleetent.cron_scheduler as cs

    monkeypatch.setattr(cs, "_CRON_YAML_PATH", tmp_path / "cron.yaml")

    scheduler = cs.CronScheduler()
    await scheduler.start()
    assert scheduler.running
    await scheduler.shutdown()


async def test_add_job_registers_in_scheduler(tmp_path, monkeypatch, isolated_schedule_db):
    import fleetent.cron_scheduler as cs

    monkeypatch.setattr(cs, "_CRON_YAML_PATH", tmp_path / "cron.yaml")

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

    monkeypatch.setattr(cs, "_CRON_YAML_PATH", tmp_path / "cron.yaml")

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

    monkeypatch.setattr(cs, "_CRON_YAML_PATH", tmp_path / "cron.yaml")

    scheduler = cs.CronScheduler()
    await scheduler.start()
    await scheduler.shutdown()
    assert not scheduler.running


# ── _fire dispatches agent_loop.run() ────────────────────────────────────────


async def test_fire_calls_agent_loop_run(tmp_path, monkeypatch):
    import fleetent.cron_scheduler as cs

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


# ── load_cron_yaml ────────────────────────────────────────────────────────────


def test_load_cron_yaml_returns_jobs(tmp_path):
    import yaml

    import fleetent.cron_scheduler as cs

    p = tmp_path / "cron.yaml"
    p.write_text(
        yaml.dump(
            {
                "jobs": [
                    {
                        "id": "j1",
                        "name": "Daily",
                        "cron": "0 9 * * *",
                        "timezone": "UTC",
                        "user_id": "u-1",
                        "message": "run",
                    },
                ]
            }
        )
    )
    jobs = cs.load_cron_yaml(p)
    assert len(jobs) == 1
    assert jobs[0]["id"] == "j1"
    assert jobs[0]["cron_expr"] == "0 9 * * *"


def test_load_cron_yaml_missing_file_returns_empty(tmp_path):
    import fleetent.cron_scheduler as cs

    jobs = cs.load_cron_yaml(tmp_path / "nonexistent.yaml")
    assert jobs == []


def test_load_cron_yaml_skips_entry_missing_required_field(tmp_path):
    import yaml

    import fleetent.cron_scheduler as cs

    p = tmp_path / "cron.yaml"
    p.write_text(
        yaml.dump(
            {
                "jobs": [
                    {
                        "id": "ok",
                        "name": "Good",
                        "cron": "* * * * *",
                        "timezone": "UTC",
                        "user_id": "u-1",
                        "message": "hi",
                    },
                    {"id": "bad"},  # missing required fields
                ]
            }
        )
    )
    jobs = cs.load_cron_yaml(p)
    assert len(jobs) == 1
    assert jobs[0]["id"] == "ok"
