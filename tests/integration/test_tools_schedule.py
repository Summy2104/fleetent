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


async def test_schedule_create_autocaptures_origin_from_session_context():
    # 5.4: create auto-fills `origin` from the inbound IM context so the reminder
    # defaults back to the originating chat/thread without an explicit notify_*.
    import fleetent.schedule_store as ss
    from fleetent.im_gateway.normalizer import SessionContext
    from fleetent.tools.registry import ToolContext

    sc = SessionContext(
        platform="slack",
        sender_id="U1",
        chat_type="channel",
        channel_name="C9",
        thread_root="T123",
    )
    with patch.object(ss, "create", return_value={"id": "x"}) as mock_create:
        payload = '{"action":"create","name":"daily","cron_expr":"0 9 * * *","message":"run"}'
        await dispatch("schedule", payload, tool_context=ToolContext(session_context=sc))

    assert mock_create.call_args.kwargs["origin"] == {
        "platform": "slack",
        "chat_id": "C9",
        "target_type": "channel",
        "thread_id": "T123",
    }


async def test_schedule_create_no_session_context_origin_none():
    import fleetent.schedule_store as ss

    with patch.object(ss, "create", return_value={"id": "x"}) as mock_create:
        payload = '{"action":"create","name":"d","cron_expr":"0 9 * * *","message":"run"}'
        await dispatch("schedule", payload)

    assert mock_create.call_args.kwargs["origin"] is None


async def test_schedule_create_origin_empty_thread_is_none():
    import fleetent.schedule_store as ss
    from fleetent.im_gateway.normalizer import SessionContext
    from fleetent.tools.registry import ToolContext

    sc = SessionContext(platform="telegram", sender_id="123", chat_type="dm", channel_name="999")
    with patch.object(ss, "create", return_value={"id": "x"}) as mock_create:
        payload = (
            '{"action":"create","name":"d","schedule_kind":"once","run_at":"+30m","message":"r"}'
        )
        await dispatch("schedule", payload, tool_context=ToolContext(session_context=sc))

    assert mock_create.call_args.kwargs["origin"] == {
        "platform": "telegram",
        "chat_id": "999",
        "target_type": "channel",
        "thread_id": None,
    }


async def test_schedule_create_explicit_notify_coexists_with_auto_origin():
    # Explicit deliver and auto origin coexist: deliver wins at fire time, origin is
    # still captured as the fallback.
    import fleetent.schedule_store as ss
    from fleetent.im_gateway.normalizer import SessionContext
    from fleetent.tools.registry import ToolContext

    sc = SessionContext(platform="slack", sender_id="U1", chat_type="dm", channel_name="D5")
    with patch.object(ss, "create", return_value={"id": "x"}) as mock_create:
        payload = (
            '{"action":"create","name":"r","cron_expr":"0 9 * * 1","message":"report",'
            '"notify_platform":"slack","notify_target":"C9","notify_target_type":"channel"}'
        )
        await dispatch("schedule", payload, tool_context=ToolContext(session_context=sc))

    kwargs = mock_create.call_args.kwargs
    assert kwargs["deliver"] == {
        "mode": "explicit",
        "platform": "slack",
        "target": "C9",
        "target_type": "channel",
    }
    assert kwargs["origin"] == {
        "platform": "slack",
        "chat_id": "D5",
        "target_type": "channel",
        "thread_id": None,
    }
