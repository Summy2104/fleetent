"""_fire threads the fire-time connector snapshot into the agent run (AAA-8039).

A scheduled task whose message asks the agent to send an IM message must have the
live connectors available to outbound tools inside the run — otherwise the run reports
"no connector available" and the task's intent silently fails.
"""

from __future__ import annotations

from unittest.mock import AsyncMock


def _make_user(user_id: str, tenant_id: str = "default"):
    from fleetent import user_store

    return user_store.User(
        id=user_id, name="T", created_at="2024-01-01",
        status="active", tenant_id=tenant_id,
    )


def _task(**over):
    base = {
        "id": "t-conn", "user_id": "u1", "message": "发条消息到频道",
        "session_id": None, "agent_name": None, "deliver": None, "origin": None,
    }
    base.update(over)
    return base


async def test_fire_passes_connectors_to_agent_loop_run(monkeypatch) -> None:
    import fleetent.runtime.loop as agent_loop
    import fleetent.session.manager as session_mgr
    from fleetent import cron_scheduler, user_store

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _make_user(uid))
    monkeypatch.setattr(session_mgr, "save", AsyncMock())

    captured: dict = {}

    async def _fake_run(messages, **kwargs):
        captured.update(kwargs)
        return "[SILENT]"

    monkeypatch.setattr(agent_loop, "run", _fake_run)

    sentinel = object()
    await cron_scheduler._fire(_task(), connectors={"slack": sentinel})

    assert captured.get("outbound_connectors") == {"slack": sentinel}, (
        "fired run must receive the fire-time connector snapshot as outbound_connectors"
    )


async def test_fire_without_connectors_passes_empty_mapping(monkeypatch) -> None:
    import fleetent.runtime.loop as agent_loop
    import fleetent.session.manager as session_mgr
    from fleetent import cron_scheduler, user_store

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _make_user(uid))
    monkeypatch.setattr(session_mgr, "save", AsyncMock())

    captured: dict = {}

    async def _fake_run(messages, **kwargs):
        captured.update(kwargs)
        return "[SILENT]"

    monkeypatch.setattr(agent_loop, "run", _fake_run)

    await cron_scheduler._fire(_task(), connectors=None)

    assert captured.get("outbound_connectors") == {}, (
        "no IM scenario must degrade to an empty mapping, not None"
    )
