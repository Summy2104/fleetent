"""Tests for cron user-status recheck + Principal production (task 5.1).

Verifies that _fire:
- Skips execution when the task's user is blocked or missing (deleted).
- Passes a Principal to loop.run (not a bare user_id string) when the user is active.
"""

from __future__ import annotations

from unittest.mock import AsyncMock


def _make_user(user_id: str, status: str = "active", tenant_id: str = "default"):
    from fleetent import user_store

    return user_store.User(
        id=user_id, name="Test", api_key="k", created_at="2024-01-01",
        status=status, tenant_id=tenant_id,
    )


# ── _resolve_cron_principal unit tests ────────────────────────────────────────


def test_resolve_cron_principal_returns_none_for_blocked_user(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.cron_scheduler import _resolve_cron_principal

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _make_user(uid, status="blocked"))
    assert _resolve_cron_principal("u1") is None


def test_resolve_cron_principal_returns_none_when_user_missing(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.cron_scheduler import _resolve_cron_principal

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: None)
    assert _resolve_cron_principal("ghost") is None


def test_resolve_cron_principal_returns_principal_for_active_user(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.cron_scheduler import _resolve_cron_principal
    from fleetent.identity import Principal

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _make_user(uid, tenant_id="acme"))
    result = _resolve_cron_principal("u2")
    assert result == Principal(user_id="u2", tenant_id="acme")


# ── _fire integration: blocked user → no _agent_run call ──────────────────────


async def test_fire_skips_agent_run_when_user_blocked(monkeypatch) -> None:
    from fleetent import cron_scheduler, user_store

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _make_user(uid, status="blocked"))

    called: list = []

    async def _fake_agent_run(*args, **kwargs):
        called.append(kwargs)
        return "reply"

    monkeypatch.setattr(cron_scheduler, "_agent_run", _fake_agent_run)

    task = {"id": "t1", "user_id": "u3", "message": "hello", "session_id": None,
            "agent_name": None, "deliver": None, "origin": None}
    await cron_scheduler._fire(task)
    assert called == [], "blocked user must not trigger _agent_run"


# ── _fire integration: active user → Principal passed to _agent_run ───────────


async def test_fire_passes_principal_to_agent_run_for_active_user(monkeypatch) -> None:
    from fleetent import cron_scheduler, user_store
    from fleetent.identity import Principal
    import fleetent.session.manager as session_mgr

    monkeypatch.setattr(user_store, "get_by_id", lambda uid: _make_user(uid, tenant_id="default"))

    captured: dict = {}

    async def _fake_agent_run(*args, **kwargs):
        captured.update(kwargs)
        return "[SILENT]"

    monkeypatch.setattr(cron_scheduler, "_agent_run", _fake_agent_run)
    monkeypatch.setattr(session_mgr, "save", AsyncMock())

    task = {"id": "t2", "user_id": "u4", "message": "ping", "session_id": None,
            "agent_name": None, "deliver": None, "origin": None}
    await cron_scheduler._fire(task)

    assert "principal" in captured, "_agent_run must receive principal= kwarg"
    p = captured["principal"]
    assert isinstance(p, Principal)
    assert p.user_id == "u4"
    assert p.tenant_id == "default"
