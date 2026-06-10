"""Tests for CronScheduler and _fire dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fleetent.identity import Principal

_STUB_PRINCIPAL = Principal(user_id="u-1", tenant_id="default")

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
    monkeypatch.setattr(cs, "_resolve_cron_principal", lambda uid: _STUB_PRINCIPAL)
    run_mock = AsyncMock(return_value="reply")
    monkeypatch.setattr(cs, "_agent_run", run_mock)

    task = {
        "id": "t1",
        "name": "n",
        "cron_expr": "* * * * *",
        "timezone": "UTC",
        "user_id": "u-1",
        "agent_name": "bot",
        "message": "hello from cron",
        "enabled": 1,
        "source": "dynamic",
    }

    await cs._fire(task)

    run_mock.assert_called_once()
    call_kwargs = run_mock.call_args[1]
    assert call_kwargs["principal"] == _STUB_PRINCIPAL
    assert call_kwargs.get("agent_name") == "bot"


async def test_fire_message_in_user_content(tmp_path, monkeypatch):
    import fleetent.cron_scheduler as cs
    import fleetent.session.manager as session_mgr

    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(cs, "_resolve_cron_principal", lambda uid: _STUB_PRINCIPAL)
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


def test_legacy_cron_yaml_path_is_removed():
    import fleetent.cron_scheduler as cs

    assert not hasattr(cs, "LEGACY_CRON_CONFIG_PATH")


def test_cron_yaml_loader_is_removed():
    import fleetent.cron_scheduler as cs

    assert not hasattr(cs, "load_cron_yaml")


async def test_start_respects_disabled_scheduling_setting(isolated_schedule_db):
    import fleetent.cron_scheduler as cs
    from fleetent.config import SchedulingSettings

    scheduler = cs.CronScheduler(settings=SchedulingSettings(enabled=False))

    await scheduler.start()

    assert not scheduler.running


# ── spillover cleanup maintenance job ────────────────────────────────────────


async def test_start_registers_spillover_cleanup_job(isolated_schedule_db):
    import fleetent.cron_scheduler as cs

    scheduler = cs.CronScheduler()
    await scheduler.start()

    job = scheduler.get_job("__maintenance_spillover_cleanup__")
    assert job is not None

    await scheduler.shutdown()


async def test_spillover_cleanup_job_invokes_cleanup_spillover(
    tmp_path, monkeypatch, isolated_schedule_db
):
    import fleetent.cron_scheduler as cs
    import fleetent.tools.result_truncation as trt

    # Redirect SPILLOVER_DIR so job.func() operates on tmp_path, not real data dir.
    spillover = tmp_path / "spillover"
    spillover.mkdir()
    monkeypatch.setattr(trt, "SPILLOVER_DIR", spillover)

    scheduler = cs.CronScheduler()
    await scheduler.start()

    job = scheduler.get_job("__maintenance_spillover_cleanup__")
    assert job is not None

    # Directly invoke the job function — verifies multi-module wiring:
    # cron_scheduler._register_maintenance_jobs → result_truncation.cleanup_spillover
    job.func()  # must not raise

    await scheduler.shutdown()


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


# ── schedule kinds: cron / once / interval (agent-owned-scheduled-tasks) ──────


async def test_register_once_uses_date_trigger(isolated_schedule_db):
    import fleetent.cron_scheduler as cs

    scheduler = cs.CronScheduler()
    await scheduler.start()
    scheduler.add_job(
        {
            "id": "once-1",
            "name": "t",
            "schedule_kind": "once",
            "run_at": "2099-01-01T00:00:00",
            "timezone": "UTC",
            "user_id": "u-1",
            "message": "ping",
            "enabled": 1,
            "source": "tool",
        }
    )
    job = scheduler.get_job("once-1")
    assert job is not None
    assert type(job.trigger).__name__ == "DateTrigger"
    await scheduler.shutdown()


async def test_register_interval_uses_interval_trigger(isolated_schedule_db):
    import fleetent.cron_scheduler as cs

    scheduler = cs.CronScheduler()
    await scheduler.start()
    scheduler.add_job(
        {
            "id": "iv-1",
            "name": "t",
            "schedule_kind": "interval",
            "interval_seconds": 5400,
            "timezone": "UTC",
            "user_id": "u-1",
            "message": "ping",
            "enabled": 1,
            "source": "tool",
        }
    )
    job = scheduler.get_job("iv-1")
    assert job is not None
    assert type(job.trigger).__name__ == "IntervalTrigger"
    await scheduler.shutdown()


async def test_agent_task_job_has_misfire_params(isolated_schedule_db):
    import fleetent.cron_scheduler as cs

    scheduler = cs.CronScheduler()
    await scheduler.start()
    scheduler.add_job(
        {
            "id": "mp-1",
            "name": "t",
            "schedule_kind": "cron",
            "cron_expr": "0 9 * * *",
            "timezone": "UTC",
            "user_id": "u-1",
            "message": "ping",
            "enabled": 1,
            "source": "tool",
        }
    )
    job = scheduler.get_job("mp-1")
    assert job is not None
    assert job.coalesce is True
    assert job.misfire_grace_time and job.misfire_grace_time > 0
    assert job.max_instances == 1
    await scheduler.shutdown()


def test_parse_run_at_accepts_relative_duration():
    import datetime

    import fleetent.cron_scheduler as cs

    before = datetime.datetime.now(datetime.UTC)
    dt = cs._parse_run_at("+30m")
    delta = (dt - before).total_seconds()
    assert 29 * 60 <= delta <= 31 * 60


def test_parse_run_at_accepts_iso_timestamp():
    import fleetent.cron_scheduler as cs

    dt = cs._parse_run_at("2099-01-01T00:00:00")
    assert dt.year == 2099 and dt.month == 1 and dt.day == 1


# ── fire-time delivery (scheduled-task-delivery) ──────────────────────────────


async def test_fire_delivers_reply_to_origin(tmp_path, monkeypatch):
    import fleetent.cron_scheduler as cs
    import fleetent.session.manager as session_mgr

    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(cs, "_resolve_cron_principal", lambda uid: _STUB_PRINCIPAL)
    monkeypatch.setattr(cs, "_agent_run", AsyncMock(return_value="your standup is at 9"))
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(cs.outbound, "send_to", send)
    monkeypatch.setattr(cs._store, "update_run_state", lambda *a, **k: None)

    task = {
        "id": "d1",
        "message": "remind standup",
        "user_id": "u-1",
        "session_id": None,
        "origin": {"platform": "slack", "chat_id": "U123"},
        "deliver": None,
    }
    conn = object()
    await cs._fire(task, connectors={"slack": conn})

    send.assert_awaited_once()
    args, kwargs = send.call_args
    assert args[0] == "slack" and args[1] is conn and args[2] == "U123"
    assert args[3] == "your standup is at 9"
    assert kwargs.get("target_type") == "user"


async def test_fire_explicit_deliver_to_channel(tmp_path, monkeypatch):
    import fleetent.cron_scheduler as cs
    import fleetent.session.manager as session_mgr

    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(cs, "_resolve_cron_principal", lambda uid: _STUB_PRINCIPAL)
    monkeypatch.setattr(cs, "_agent_run", AsyncMock(return_value="daily report"))
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(cs.outbound, "send_to", send)
    monkeypatch.setattr(cs._store, "update_run_state", lambda *a, **k: None)

    task = {
        "id": "d2",
        "message": "report",
        "user_id": "u-1",
        "session_id": None,
        "origin": {"platform": "slack", "chat_id": "U123"},
        "deliver": {
            "mode": "explicit",
            "platform": "slack",
            "target": "C999",
            "target_type": "channel",
        },
    }
    await cs._fire(task, connectors={"slack": object()})

    args, kwargs = send.call_args
    assert args[2] == "C999"
    assert kwargs.get("target_type") == "channel"


async def test_fire_silent_reply_suppresses_delivery(tmp_path, monkeypatch):
    import fleetent.cron_scheduler as cs
    import fleetent.session.manager as session_mgr

    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(cs, "_resolve_cron_principal", lambda uid: _STUB_PRINCIPAL)
    monkeypatch.setattr(cs, "_agent_run", AsyncMock(return_value="[SILENT]"))
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(cs.outbound, "send_to", send)
    statuses = []
    monkeypatch.setattr(
        cs._store, "update_run_state", lambda tid, **k: statuses.append(k.get("last_status"))
    )

    task = {
        "id": "d3",
        "message": "check changes",
        "user_id": "u-1",
        "session_id": None,
        "origin": {"platform": "slack", "chat_id": "U123"},
    }
    await cs._fire(task, connectors={"slack": object()})

    send.assert_not_awaited()
    assert statuses == ["ok"]


async def test_fire_missing_connector_records_error(tmp_path, monkeypatch):
    import fleetent.cron_scheduler as cs
    import fleetent.session.manager as session_mgr

    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(cs, "_resolve_cron_principal", lambda uid: _STUB_PRINCIPAL)
    monkeypatch.setattr(cs, "_agent_run", AsyncMock(return_value="hi"))
    captured = {}
    monkeypatch.setattr(
        cs._store,
        "update_run_state",
        lambda tid, **k: captured.update(k),
    )

    task = {
        "id": "d4",
        "message": "ping",
        "user_id": "u-1",
        "session_id": None,
        "origin": {"platform": "telegram", "chat_id": "555"},
    }
    # No telegram connector available at fire time.
    await cs._fire(task, connectors={})

    assert captured.get("last_status") == "error"
    assert "connector" in (captured.get("last_error") or "")
