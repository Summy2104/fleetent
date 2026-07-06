"""Unit: generate fires suppress outbound delivery tools (generate-fires-exclude-outbound-tools).

A `generate` task produces the notification body and the SCHEDULER delivers it — so the run
must not expose `send_im_message`/`send_file` (else the model self-delivers and duplicates the
broadcast). An `action` task retains them (it delivers via its own tools).
"""

from __future__ import annotations

from unittest.mock import AsyncMock


def _schemas(*names):
    return [{"type": "function", "function": {"name": n}} for n in names]


def _names(schemas):
    return [s["function"]["name"] for s in schemas]


# --- Task 1: schema filter helper ---


def test_filter_removes_outbound_when_suppressed():
    from fleetent.runtime.loop import _filter_outbound_tools

    out = _filter_outbound_tools(
        _schemas("read_file", "send_im_message", "send_file", "run_code"), suppress=True
    )
    assert _names(out) == ["read_file", "run_code"]


def test_filter_keeps_all_when_not_suppressed():
    from fleetent.runtime.loop import _filter_outbound_tools

    names = ["read_file", "send_im_message", "send_file", "run_code"]
    out = _filter_outbound_tools(_schemas(*names), suppress=False)
    assert _names(out) == names


# --- Task 2: _fire threads suppression by task_type ---


def _make_user(user_id: str, tenant_id: str = "default"):
    from fleetent import user_store

    return user_store.User(
        id=user_id, name="T", created_at="2024-01-01", status="active", tenant_id=tenant_id
    )


def _task(**over):
    base = {
        "id": "t1",
        "user_id": "u1",
        "message": "做点事",
        "session_id": None,
        "agent_name": None,
        "deliver": None,
        "origin": None,
    }
    base.update(over)
    return base


async def _capture_fire(monkeypatch, task):
    import fleetent.runtime.loop as agent_loop
    import fleetent.session.manager as session_mgr
    from fleetent import cron_scheduler, user_store

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _make_user(uid))
    monkeypatch.setattr(session_mgr, "save", AsyncMock())
    monkeypatch.setattr(session_mgr, "load", AsyncMock(return_value=[]))

    captured: dict = {}

    async def _fake_run(messages, **kwargs):
        captured.update(kwargs)
        return "[SILENT]"

    monkeypatch.setattr(agent_loop, "run", _fake_run)
    await cron_scheduler._fire(task, connectors={"slack": object()})
    return captured


async def test_generate_fire_suppresses_outbound(monkeypatch):
    captured = await _capture_fire(monkeypatch, _task(task_type="generate"))
    assert captured.get("suppress_outbound_tools") is True


async def test_action_fire_keeps_outbound(monkeypatch):
    captured = await _capture_fire(monkeypatch, _task(task_type="action"))
    assert captured.get("suppress_outbound_tools") is False


# ── fired runs exclude the schedule tool (cron-delivery-governance F4.4) ─────────
# Both generate and action fires must drop `schedule` from their tool schema so a
# fired run cannot create/modify scheduled tasks (self-replication guard).


def test_filter_excludes_named_tools_regardless_of_suppress():
    from fleetent.runtime.loop import _filter_outbound_tools

    out = _filter_outbound_tools(
        _schemas("read_file", "send_im_message", "schedule", "run_code"),
        suppress=False,
        exclude=frozenset({"schedule"}),
    )
    assert _names(out) == ["read_file", "send_im_message", "run_code"]


def test_filter_combines_suppress_and_exclude():
    from fleetent.runtime.loop import _filter_outbound_tools

    out = _filter_outbound_tools(
        _schemas("read_file", "send_im_message", "send_file", "schedule", "run_code"),
        suppress=True,
        exclude=frozenset({"schedule"}),
    )
    assert _names(out) == ["read_file", "run_code"]


async def test_generate_fire_excludes_schedule_tool(monkeypatch):
    captured = await _capture_fire(monkeypatch, _task(task_type="generate"))
    assert captured.get("exclude_tools") == frozenset({"schedule"})


async def test_action_fire_excludes_schedule_tool(monkeypatch):
    captured = await _capture_fire(monkeypatch, _task(task_type="action"))
    assert captured.get("exclude_tools") == frozenset({"schedule"})
