from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fleetent.im_gateway.normalizer import SessionContext
from fleetent.tools import builtin_tools
from fleetent.tools.registry import ToolContext


def _ctx() -> ToolContext:
    return ToolContext(
        session_context=SessionContext(
            platform="slack",
            sender_id="U1",
            channel_name="C1",
            thread_root="123.456",
        ),
        principal=SimpleNamespace(user_id="owner-1"),
    )


async def test_schedule_create_handles_saved_registered_and_validation_error(monkeypatch) -> None:
    created: list[dict[str, object]] = []
    monkeypatch.setattr(
        "fleetent.cron_scheduler.create_task",
        lambda **kwargs: created.append(kwargs) or {"id": "task-1"},
    )

    monkeypatch.setattr("fleetent.cron_scheduler.current", lambda: None)
    saved = await builtin_tools.schedule(
        action="create",
        name="daily",
        schedule_kind="once",
        run_at="+30m",
        message="hello",
        notify_platform="slack",
        notify_target="C1",
        notify_target_type="channel",
        task_type="notify",
        notify_text="ship it",
        tool_context=_ctx(),
    )
    assert "saved" in saved
    assert created[0]["user_id"] == "owner-1"
    assert created[0]["origin"] == {
        "platform": "slack",
        "chat_id": "C1",
        "target_type": "channel",
        "thread_id": "123.456",
    }
    assert created[0]["deliver"] == {
        "mode": "explicit",
        "platform": "slack",
        "target": "C1",
        "target_type": "channel",
    }

    monkeypatch.setattr("fleetent.cron_scheduler.current", lambda: object())
    registered = await builtin_tools.schedule(action="create", name="daily", cron_expr="0 9 * * *")
    assert "created and registered" in registered

    def boom(**kwargs):
        raise ValueError("notify_text required")

    monkeypatch.setattr("fleetent.cron_scheduler.create_task", boom)
    err = await builtin_tools.schedule(action="create", name="daily", task_type="notify")
    assert err == "error: notify_text required"


async def test_schedule_list_remove_pause_resume_run_now_and_unknown(monkeypatch) -> None:
    monkeypatch.setattr("fleetent.cron_scheduler.list_tasks", lambda include_disabled=False: [])
    assert await builtin_tools.schedule(action="list") == "No scheduled tasks"

    monkeypatch.setattr(
        "fleetent.cron_scheduler.list_tasks",
        lambda include_disabled=False: [
            {"id": "t1", "name": "daily", "schedule_kind": "cron", "enabled": True},
            {"id": "t2", "name": "weekly", "schedule_kind": "once", "enabled": False},
        ],
    )
    listed = await builtin_tools.schedule(action="list")
    assert "t1 | daily | cron | enabled" in listed
    assert "t2 | weekly | once | paused" in listed

    monkeypatch.setattr("fleetent.cron_scheduler.remove_task", lambda task_id: task_id == "t1")
    assert await builtin_tools.schedule(action="remove", task_id="t1") == "Scheduled task 't1' removed"
    assert "not found" in await builtin_tools.schedule(action="remove", task_id="missing")

    monkeypatch.setattr(
        "fleetent.cron_scheduler.set_task_enabled",
        lambda task_id, enabled: task_id == "t1",
    )
    assert await builtin_tools.schedule(action="pause", task_id="t1") == "Scheduled task 't1' paused"
    assert await builtin_tools.schedule(action="resume", task_id="t1") == "Scheduled task 't1' resumed"
    assert "not found" in await builtin_tools.schedule(action="pause", task_id="missing")

    monkeypatch.setattr(
        "fleetent.cron_scheduler.run_task_now",
        AsyncMock(side_effect=lambda task_id: task_id == "t1"),
    )
    assert await builtin_tools.schedule(action="run_now", task_id="t1") == "Scheduled task 't1' fired"
    assert "not found" in await builtin_tools.schedule(action="run_now", task_id="missing")

    assert "unknown action" in await builtin_tools.schedule(action="bogus")
