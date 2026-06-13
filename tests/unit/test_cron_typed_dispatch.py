"""_fire dispatches by task_type: notify (no agent) / generate (deliver) / action (no broadcast)."""

from __future__ import annotations

from unittest.mock import AsyncMock


def _user(uid, tenant="default"):
    from fleetent import user_store

    return user_store.User(
        id=uid, name="T", created_at="2024-01-01", status="active", tenant_id=tenant
    )


def _task(**over):
    base = {
        "id": "t",
        "user_id": "u1",
        "message": "do work",
        "session_id": None,
        "agent_name": None,
        "deliver": {
            "mode": "explicit",
            "platform": "slack",
            "target": "C1",
            "target_type": "channel",
        },
        "origin": None,
        "task_type": "generate",
        "notify_text": None,
    }
    base.update(over)
    return base


async def test_notify_delivers_text_without_agent(monkeypatch):
    from fleetent import cron_scheduler, user_store

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _user(uid))

    async def _no_agent(*a, **k):
        raise AssertionError("notify must not run the agent")

    delivered: dict = {}

    async def _fake_deliver(task, reply, connectors):
        delivered["reply"] = reply
        return None

    monkeypatch.setattr(cron_scheduler, "_agent_run", _no_agent)
    monkeypatch.setattr(cron_scheduler, "_deliver", _fake_deliver)

    await cron_scheduler._fire(
        _task(task_type="notify", notify_text="开晨会啦", message=""),
        connectors={"slack": object()},
    )
    assert delivered["reply"] == "开晨会啦"


async def test_generate_injects_delivery_statement_and_delivers(monkeypatch):
    import fleetent.session.manager as session_mgr
    from fleetent import cron_scheduler, user_store

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _user(uid))
    monkeypatch.setattr(session_mgr, "save", AsyncMock())

    captured: dict = {}

    async def _fake_agent_run(messages, **k):
        captured["messages"] = messages
        return "GENERATED BODY"

    delivered: dict = {}

    async def _fake_deliver(task, reply, connectors):
        delivered["reply"] = reply
        return None

    monkeypatch.setattr(cron_scheduler, "_agent_run", _fake_agent_run)
    monkeypatch.setattr(cron_scheduler, "_deliver", _fake_deliver)

    await cron_scheduler._fire(_task(task_type="generate"), connectors={"slack": object()})

    blob = " ".join(m.get("content", "") for m in captured["messages"])
    assert "SILENT" in blob, "generate run must carry the delivery statement (mentions [SILENT])"
    assert delivered["reply"] == "GENERATED BODY"


async def test_action_does_not_broadcast(monkeypatch):
    import fleetent.session.manager as session_mgr
    from fleetent import cron_scheduler, user_store

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _user(uid))
    monkeypatch.setattr(session_mgr, "save", AsyncMock())

    async def _fake_agent_run(messages, **k):
        return "I sent the DMs myself"

    deliver_called = {"n": 0}

    async def _fake_deliver(task, reply, connectors):
        deliver_called["n"] += 1
        return None

    monkeypatch.setattr(cron_scheduler, "_agent_run", _fake_agent_run)
    monkeypatch.setattr(cron_scheduler, "_deliver", _fake_deliver)

    await cron_scheduler._fire(_task(task_type="action"), connectors={"slack": object()})
    assert deliver_called["n"] == 0, "action task reply must not be broadcast by the scheduler"
