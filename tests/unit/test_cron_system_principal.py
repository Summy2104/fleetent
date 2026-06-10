"""Tests for SYSTEM_PRINCIPAL on infrastructure cron tasks (task 5.2).

Infrastructure tasks store user_id="system" in scheduled_tasks. The scheduler
must use SYSTEM_PRINCIPAL directly — no user_store lookup, no blocking.
"""

from __future__ import annotations


def test_resolve_cron_principal_system_returns_system_principal() -> None:
    from fleetent.cron_scheduler import _resolve_cron_principal
    from fleetent.identity import SYSTEM_PRINCIPAL

    result = _resolve_cron_principal("system")
    assert result is SYSTEM_PRINCIPAL


def test_resolve_cron_principal_system_never_calls_user_store(monkeypatch) -> None:
    """user_store.get_by_id must not be called when user_id is 'system'."""
    from fleetent import user_store
    from fleetent.cron_scheduler import _resolve_cron_principal

    calls: list = []
    monkeypatch.setattr(user_store, "get_by_id", lambda uid: calls.append(uid) or None)
    _resolve_cron_principal("system")
    assert calls == [], "system path must bypass user_store lookup"


async def test_fire_system_task_runs_without_user_lookup(monkeypatch) -> None:
    """A task with user_id='system' fires using SYSTEM_PRINCIPAL without DB access."""
    from fleetent import cron_scheduler, user_store
    from fleetent.identity import SYSTEM_PRINCIPAL
    from unittest.mock import AsyncMock
    import fleetent.session.manager as session_mgr

    # Ensure get_by_id is never called
    calls: list = []
    monkeypatch.setattr(user_store, "get_by_id", lambda uid: calls.append(uid) or None)

    captured: dict = {}

    async def _fake_agent_run(*args, **kwargs):
        captured.update(kwargs)
        return "[SILENT]"

    monkeypatch.setattr(cron_scheduler, "_agent_run", _fake_agent_run)
    monkeypatch.setattr(session_mgr, "save", AsyncMock())

    task = {"id": "sys-t1", "user_id": "system", "message": "ttl-cleanup",
            "session_id": None, "agent_name": None, "deliver": None, "origin": None}
    await cron_scheduler._fire(task)

    assert calls == [], "system task must not hit user_store"
    assert captured.get("principal") is SYSTEM_PRINCIPAL
