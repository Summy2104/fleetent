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


# ── half-set notify_platform/notify_target rejection (cron-delivery-governance F4.1) ──


async def test_schedule_create_only_notify_target_is_rejected():
    """notify_target without notify_platform must error, not silently fall back to origin
    (AAA-8279 root cause: the half-set was previously ignored and delivery fell back to
    the creation channel, which reads as "wrong channel" to the user)."""
    import fleetent.schedule_store as ss

    with patch.object(ss, "create") as mock_create:
        payload = (
            '{"action":"create","name":"rep","cron_expr":"0 9 * * *",'
            '"message":"report","notify_target":"C9"}'
        )
        result = await dispatch("schedule", payload)

    mock_create.assert_not_called()
    assert "error" in result.lower()
    assert "notify_platform" in result


async def test_schedule_create_only_notify_platform_is_rejected():
    import fleetent.schedule_store as ss

    with patch.object(ss, "create") as mock_create:
        payload = (
            '{"action":"create","name":"rep","cron_expr":"0 9 * * *",'
            '"message":"report","notify_platform":"slack"}'
        )
        result = await dispatch("schedule", payload)

    mock_create.assert_not_called()
    assert "error" in result.lower()
    assert "notify_target" in result


async def test_schedule_create_neither_notify_param_is_fine():
    """Omitting both is the normal "deliver to origin" path — not a half-set."""
    import fleetent.schedule_store as ss

    with patch.object(ss, "create", return_value={"id": "x"}) as mock_create:
        payload = '{"action":"create","name":"rep","cron_expr":"0 9 * * *","message":"report"}'
        result = await dispatch("schedule", payload)

    mock_create.assert_called_once()
    assert "error" not in result.lower()


# ── create echo明示/警示投递目标 (cron-delivery-governance F4.3) ──────────────


async def test_schedule_create_echoes_explicit_target():
    import fleetent.schedule_store as ss

    with patch.object(ss, "create", return_value={"id": "x"}):
        payload = (
            '{"action":"create","name":"rep","cron_expr":"0 9 * * *","message":"report",'
            '"notify_platform":"slack","notify_target":"C123","notify_target_type":"channel"}'
        )
        result = await dispatch("schedule", payload)

    assert "slack:C123(channel)" in result


async def test_schedule_create_echoes_origin_fallback():
    import fleetent.schedule_store as ss
    from fleetent.im_gateway.normalizer import SessionContext
    from fleetent.tools.registry import ToolContext

    sc = SessionContext(platform="slack", sender_id="U1", chat_type="dm", channel_name="D5")
    with patch.object(ss, "create", return_value={"id": "x"}):
        payload = '{"action":"create","name":"rep","cron_expr":"0 9 * * *","message":"report"}'
        result = await dispatch("schedule", payload, tool_context=ToolContext(session_context=sc))

    assert "创建会话" in result


async def test_schedule_create_generate_no_target_echoes_warning():
    """No explicit target and no capturable origin: create still succeeds (this is a
    visibility warning, not a rejection — the fire-time no_delivery_target + alert from
    fix-cron-store-and-once is the actual safety net)."""
    import fleetent.schedule_store as ss

    with patch.object(ss, "create", return_value={"id": "x"}) as mock_create:
        payload = '{"action":"create","name":"rep","cron_expr":"0 9 * * *","message":"report"}'
        result = await dispatch("schedule", payload)

    mock_create.assert_called_once()  # not rejected
    assert "⚠️" in result
    assert "无法送达" in result or "无处可去" in result


async def test_schedule_create_action_no_target_no_warning():
    """An action task delivers via its own tools — the scheduler-target warning does
    not apply to it."""
    import fleetent.schedule_store as ss

    with patch.object(ss, "create", return_value={"id": "x"}):
        payload = (
            '{"action":"create","name":"rep","cron_expr":"0 9 * * *",'
            '"message":"do it","task_type":"action"}'
        )
        result = await dispatch("schedule", payload)

    assert "⚠️" not in result


def test_legacy_schedule_task_and_cancel_task_removed():
    from fleetent.tools.registry import get_schemas

    names = {s["function"]["name"] for s in get_schemas()}
    assert "schedule" in names
    assert "schedule_task" not in names
    assert "cancel_task" not in names


# ── session binding exposed through the schedule tool (cron-hardening F6.4) ──


async def test_schedule_create_passes_session_through():
    import fleetent.schedule_store as ss

    with patch.object(ss, "create", return_value={"id": "x"}) as mock_create:
        payload = (
            '{"action":"create","name":"counter","cron_expr":"0 9 * * *",'
            '"message":"count and report","session":"cron/counter"}'
        )
        await dispatch("schedule", payload)

    assert mock_create.call_args.kwargs["session_id"] == "cron/counter"


async def test_schedule_create_without_session_defaults_to_none():
    import fleetent.schedule_store as ss

    with patch.object(ss, "create", return_value={"id": "x"}) as mock_create:
        payload = '{"action":"create","name":"rep","cron_expr":"0 9 * * *","message":"report"}'
        await dispatch("schedule", payload)

    assert mock_create.call_args.kwargs["session_id"] is None


def test_schedule_session_param_schema_describes_both_states():
    from fleetent.tools.registry import get_schemas

    schedule_schema = next(s for s in get_schemas() if s["function"]["name"] == "schedule")
    session_param = schedule_schema["function"]["parameters"]["properties"]["session"]
    desc = session_param.get("description", "")
    assert "独立" in desc
    assert "累积" in desc


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


# ── Live registration through the facade (schedule-live-registration) ────────


async def test_schedule_create_registers_live_job(isolated_schedule_db):
    import fleetent.cron_scheduler as cs
    import fleetent.schedule_store as ss

    scheduler = cs.CronScheduler()
    await scheduler.start()
    try:
        payload = '{"action":"create","name":"live","cron_expr":"0 9 * * *","message":"go"}'
        result = await dispatch("schedule", payload)

        rows = ss.list_tasks()
        assert len(rows) == 1
        assert rows[0]["id"] in result
        assert scheduler.get_job(rows[0]["id"]) is not None
    finally:
        await scheduler.shutdown()


async def test_schedule_remove_pause_resume_sync_live_job(isolated_schedule_db):
    import fleetent.cron_scheduler as cs
    import fleetent.schedule_store as ss

    scheduler = cs.CronScheduler()
    await scheduler.start()
    try:
        await dispatch(
            "schedule", '{"action":"create","name":"t","cron_expr":"0 9 * * *","message":"x"}'
        )
        task_id = ss.list_tasks()[0]["id"]

        await dispatch("schedule", f'{{"action":"pause","task_id":"{task_id}"}}')
        assert scheduler.get_job(task_id) is None

        await dispatch("schedule", f'{{"action":"resume","task_id":"{task_id}"}}')
        assert scheduler.get_job(task_id) is not None

        await dispatch("schedule", f'{{"action":"remove","task_id":"{task_id}"}}')
        assert scheduler.get_job(task_id) is None
        assert ss.get(task_id) is None
    finally:
        await scheduler.shutdown()


async def test_schedule_create_without_scheduler_degrades_honestly(isolated_schedule_db):
    import fleetent.cron_scheduler as cs
    import fleetent.schedule_store as ss

    assert cs.current() is None  # no scheduler running in this test

    payload = '{"action":"create","name":"later","cron_expr":"0 9 * * *","message":"go"}'
    result = await dispatch("schedule", payload)

    assert len(ss.list_tasks()) == 1
    assert "takes effect when the agent service is running" in result
    assert "active" not in result.lower()


def test_tools_layer_does_not_import_schedule_store():
    """Dependency guardrail: all task mutations go through the cron_scheduler facade."""
    import pathlib

    import fleetent.tools as tools_pkg

    pkg_dir = pathlib.Path(tools_pkg.__file__).parent
    offenders = [
        py.name for py in pkg_dir.glob("*.py") if "schedule_store" in py.read_text(encoding="utf-8")
    ]
    assert offenders == []


# ── Task owner stamped from the execution principal ──────────────────────────


async def test_schedule_create_owner_from_principal(isolated_schedule_db):
    import fleetent.schedule_store as ss
    from fleetent.identity import Principal
    from fleetent.tools.registry import ToolContext

    ctx = ToolContext(principal=Principal(user_id="internal-u9", tenant_id="default"))
    payload = (
        '{"action":"create","name":"t","cron_expr":"0 9 * * *",'
        '"message":"x","user_id":"model-made-this-up"}'
    )
    await dispatch("schedule", payload, tool_context=ctx)

    rows = ss.list_tasks()
    assert len(rows) == 1
    assert rows[0]["user_id"] == "internal-u9"


async def test_schedule_create_owner_falls_back_to_param_without_principal(isolated_schedule_db):
    import fleetent.schedule_store as ss
    from fleetent.tools.registry import ToolContext

    payload = (
        '{"action":"create","name":"t","cron_expr":"0 9 * * *","message":"x","user_id":"u-param"}'
    )
    await dispatch("schedule", payload, tool_context=ToolContext())

    rows = ss.list_tasks()
    assert len(rows) == 1
    assert rows[0]["user_id"] == "u-param"
