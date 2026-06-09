"""Tests for the unified `schedule` tool (agent-owned-scheduled-tasks)."""

from unittest.mock import AsyncMock, patch

import fleetent.tools  # noqa: F401 — register tools
from fleetent.tools.registry import dispatch


async def test_schedule_create_returns_task_id():
    import fleetent.schedule_store as ss

    fake_task = {"id": "uuid-123", "name": "daily"}
    with patch.object(ss, "create", return_value=fake_task) as mock_create:
        payload = (
            '{"action":"create","name":"daily","cron_expr":"0 9 * * *",'
            '"message":"run","user_id":"u-1"}'
        )
        result = await dispatch("schedule", payload)

    mock_create.assert_called_once()
    assert "uuid-123" in result


async def test_schedule_create_passes_explicit_delivery():
    import fleetent.schedule_store as ss

    with patch.object(ss, "create", return_value={"id": "x"}) as mock_create:
        payload = (
            '{"action":"create","name":"rep","cron_expr":"0 9 * * 1",'
            '"message":"report","notify_platform":"slack",'
            '"notify_target":"C9","notify_target_type":"channel"}'
        )
        await dispatch("schedule", payload)

    deliver = mock_create.call_args.kwargs["deliver"]
    assert deliver == {
        "mode": "explicit",
        "platform": "slack",
        "target": "C9",
        "target_type": "channel",
    }


async def test_schedule_remove_found():
    import fleetent.schedule_store as ss

    with patch.object(ss, "delete", return_value=True):
        result = await dispatch("schedule", '{"action":"remove","task_id":"uuid-123"}')
    assert "uuid-123" in result and "removed" in result.lower()


async def test_schedule_remove_not_found():
    import fleetent.schedule_store as ss

    with patch.object(ss, "delete", return_value=False):
        result = await dispatch("schedule", '{"action":"remove","task_id":"no-such-id"}')
    assert "no-such-id" in result and "not found" in result.lower()


async def test_schedule_pause_and_resume_toggle_enabled():
    import fleetent.schedule_store as ss

    with patch.object(ss, "set_enabled", return_value=True) as mock_set:
        await dispatch("schedule", '{"action":"pause","task_id":"t1"}')
        await dispatch("schedule", '{"action":"resume","task_id":"t1"}')

    assert mock_set.call_args_list[0].args == ("t1", False)
    assert mock_set.call_args_list[1].args == ("t1", True)


async def test_schedule_run_now_fires_task():
    import fleetent.cron_scheduler as cs
    import fleetent.schedule_store as ss

    task = {"id": "t1", "message": "m", "user_id": "u", "session_id": None}
    with (
        patch.object(ss, "get", return_value=task),
        patch.object(cs, "_fire", new_callable=AsyncMock) as mock_fire,
    ):
        result = await dispatch("schedule", '{"action":"run_now","task_id":"t1"}')

    mock_fire.assert_awaited_once()
    assert "fired" in result.lower()


async def test_schedule_unknown_action_returns_error():
    result = await dispatch("schedule", '{"action":"bogus"}')
    assert "unknown action" in result.lower()


def test_legacy_schedule_task_and_cancel_task_removed():
    from fleetent.tools.registry import get_schemas

    names = {s["function"]["name"] for s in get_schemas()}
    assert "schedule" in names
    assert "schedule_task" not in names
    assert "cancel_task" not in names
