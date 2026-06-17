"""Fire-time principal resolution for cron tasks (decouple-cron-principal-recheck).

`_resolve_cron_principal` is injection-decoupled from the platform management DB:
- Standalone (no resolver installed): trust the task's archived IM identity; never
  touch `user_store` / the management database. An empty/malformed DATABASE_URL can
  therefore never skip a fire.
- Platform (resolver installed via `set_principal_resolver`): delegate to the resolver,
  which performs the blocked/deleted revocation recheck.

The `system`/`default` short-circuits stay DB-free and resolver-free.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def _reset_principal_resolver():
    """Module-level resolver is global state — reset around every test."""
    from fleetent import cron_scheduler

    saved = cron_scheduler._principal_resolver
    cron_scheduler._principal_resolver = None
    yield
    cron_scheduler._principal_resolver = saved


def _im_origin() -> dict:
    return {"platform": "slack", "chat_id": "D0", "target_type": "channel"}


def _exploding_get_by_id(*_a, **_k):
    raise AssertionError("standalone fire path must not call user_store.get_by_id")


# ── Standalone (no resolver): trust archived IM identity, never touch a DB ─────


def test_standalone_trusts_im_identity_without_db(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.cron_scheduler import _resolve_cron_principal
    from fleetent.identity import Principal

    monkeypatch.setattr(user_store, "get_by_id", _exploding_get_by_id)
    result = _resolve_cron_principal({"id": "t", "user_id": "U09M5T71R25", "origin": _im_origin()})
    assert result == Principal(user_id="U09M5T71R25", tenant_id="default")


def test_standalone_trusts_even_without_im_origin(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.cron_scheduler import _resolve_cron_principal
    from fleetent.identity import Principal

    monkeypatch.setattr(user_store, "get_by_id", _exploding_get_by_id)
    # Agent-independence baseline: with no user-management domain, the archived identity
    # is trusted unconditionally (matching the legacy "no such table" behavior).
    assert _resolve_cron_principal({"id": "t", "user_id": "anyone", "origin": None}) == Principal(
        user_id="anyone", tenant_id="default"
    )


def test_standalone_unaffected_by_empty_database_url(monkeypatch) -> None:
    """Regression (dev incident): empty DATABASE_URL must not skip firing.

    Standalone never opens the management DB, so a malformed DATABASE_URL is irrelevant.
    """
    from fleetent import user_store
    from fleetent.cron_scheduler import _resolve_cron_principal
    from fleetent.identity import Principal

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setattr(user_store, "get_by_id", _exploding_get_by_id)
    result = _resolve_cron_principal({"id": "t", "user_id": "U1", "origin": _im_origin()})
    assert result == Principal(user_id="U1", tenant_id="default")


# ── system / default short-circuits: no resolver, no DB ───────────────────────


def test_system_user_returns_system_principal(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.cron_scheduler import _resolve_cron_principal
    from fleetent.identity import SYSTEM_PRINCIPAL

    monkeypatch.setattr(user_store, "get_by_id", _exploding_get_by_id)
    assert (
        _resolve_cron_principal({"id": "t", "user_id": "system", "origin": None})
        is SYSTEM_PRINCIPAL
    )


def test_default_user_returns_default_principal(monkeypatch) -> None:
    from fleetent import user_store
    from fleetent.cron_scheduler import _resolve_cron_principal
    from fleetent.identity import Principal

    monkeypatch.setattr(user_store, "get_by_id", _exploding_get_by_id)
    assert _resolve_cron_principal({"id": "t", "user_id": "default", "origin": None}) == Principal(
        user_id="default", tenant_id="default"
    )


# ── Platform (resolver installed): delegate to the injected resolver ──────────


def test_delegates_to_injected_resolver() -> None:
    from fleetent import cron_scheduler
    from fleetent.cron_scheduler import _resolve_cron_principal, set_principal_resolver
    from fleetent.identity import Principal

    seen: list = []

    def _resolver(task):
        seen.append(task["id"])
        return Principal(user_id="u9", tenant_id="acme")

    set_principal_resolver(_resolver)
    assert cron_scheduler._principal_resolver is _resolver
    result = _resolve_cron_principal({"id": "tX", "user_id": "u9", "origin": None})
    assert result == Principal(user_id="u9", tenant_id="acme")
    assert seen == ["tX"]


def test_injected_resolver_can_reject() -> None:
    from fleetent.cron_scheduler import _resolve_cron_principal, set_principal_resolver

    set_principal_resolver(lambda task: None)  # e.g. blocked creator
    assert _resolve_cron_principal({"id": "t", "user_id": "u1", "origin": _im_origin()}) is None


def test_injected_resolver_error_fails_closed() -> None:
    from fleetent.cron_scheduler import _resolve_cron_principal, set_principal_resolver

    def _boom(task):
        raise RuntimeError("database is locked")

    set_principal_resolver(_boom)  # platform lookup failed → must not fire unverified
    assert _resolve_cron_principal({"id": "t", "user_id": "u1", "origin": _im_origin()}) is None


# ── _fire integration via the new model ───────────────────────────────────────


async def test_fire_passes_principal_for_standalone_im_task(monkeypatch) -> None:
    import fleetent.session.manager as session_mgr
    from fleetent import cron_scheduler
    from fleetent.identity import Principal

    captured: dict = {}

    async def _fake_agent_run(*args, **kwargs):
        captured.update(kwargs)
        return "[SILENT]"

    monkeypatch.setattr(cron_scheduler, "_agent_run", _fake_agent_run)
    monkeypatch.setattr(session_mgr, "save", AsyncMock())

    task = {
        "id": "t2",
        "user_id": "u4",
        "message": "ping",
        "session_id": None,
        "agent_name": None,
        "deliver": None,
        "origin": _im_origin(),
    }
    await cron_scheduler._fire(task)

    p = captured.get("principal")
    assert isinstance(p, Principal)
    assert p.user_id == "u4"
    assert p.tenant_id == "default"


async def test_fire_skips_when_resolver_rejects(monkeypatch) -> None:
    from fleetent import cron_scheduler
    from fleetent.cron_scheduler import set_principal_resolver

    set_principal_resolver(lambda task: None)  # blocked/missing creator

    called: list = []

    async def _fake_agent_run(*args, **kwargs):
        called.append(kwargs)
        return "reply"

    monkeypatch.setattr(cron_scheduler, "_agent_run", _fake_agent_run)

    task = {
        "id": "t1",
        "user_id": "u3",
        "message": "hello",
        "session_id": None,
        "agent_name": None,
        "deliver": None,
        "origin": _im_origin(),
    }
    await cron_scheduler._fire(task)
    assert called == [], "rejected principal must not trigger _agent_run"
