"""Unit tests for Group 7 (7.3): transparent per-user token self-refresh decision logic.

The client's ``_ensure_fresh_user_token`` is the single pre-call gate: a live token (or one
with no expiry) passes untouched; an expired-but-refreshable token is refreshed in place via
the injected refresher (transparent to the caller); a missing token or a genuine refresh
failure returns False (drives this user's authorization). A transient refresh error keeps the
stale token and still proceeds (degrades, never crashes). The token store + refresher seam
are stubbed; no DB / network here.
"""

from __future__ import annotations

import fleetent.integrations.mcp.client as mc
from fleetent.integrations.mcp.client import McpServerConfig
from fleetent.integrations.mcp.per_user_tokens import UserToken


def _server(sid: str = "puo") -> McpServerConfig:
    return McpServerConfig(
        id=sid,
        transport="http",
        url="https://host/mcp",
        auth_type="oauth2",
        oauth_grant="authorization_code",
        authorization_endpoint="https://as.internal/authorize",
        token_url="https://as.internal/token",
        client_id="client-123",
        scope="read",
    )


def _fixed_now(monkeypatch, value: float) -> None:
    monkeypatch.setattr(mc.time, "time", lambda: value)


async def test_no_user_id_is_false(monkeypatch):
    monkeypatch.setattr(mc, "set_token_refresher", mc.set_token_refresher)
    assert await mc._ensure_fresh_user_token(_server(), None, "ag1") is False


async def test_missing_token_is_false(monkeypatch):
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: None)
    assert await mc._ensure_fresh_user_token(_server(), "uA", "ag1") is False


async def test_live_token_passes_without_refresh(monkeypatch):
    _fixed_now(monkeypatch, 100.0)
    monkeypatch.setattr(
        mc, "resolve_user_token", lambda *a, **k: UserToken("at", "rt", 200.0, "read")
    )
    called = []

    async def _refresher(*a):
        called.append(a)
        return None

    mc.set_token_refresher(_refresher)
    try:
        assert await mc._ensure_fresh_user_token(_server(), "uA", "ag1") is True
        assert called == []  # not expired → no refresh
    finally:
        mc.set_token_refresher(None)


async def test_token_without_expiry_is_never_refreshed(monkeypatch):
    _fixed_now(monkeypatch, 100.0)
    monkeypatch.setattr(
        mc, "resolve_user_token", lambda *a, **k: UserToken("at", "rt", None, "read")
    )
    called = []

    async def _refresher(*a):
        called.append(a)
        return None

    mc.set_token_refresher(_refresher)
    try:
        assert await mc._ensure_fresh_user_token(_server(), "uA", "ag1") is True
        assert called == []
    finally:
        mc.set_token_refresher(None)


async def test_expired_token_is_refreshed(monkeypatch):
    _fixed_now(monkeypatch, 300.0)
    monkeypatch.setattr(
        mc, "resolve_user_token", lambda *a, **k: UserToken("old", "rt", 200.0, "read")
    )
    seen: list[tuple] = []

    async def _refresher(server_id, user_id, agent_id, token):
        seen.append((server_id, user_id, agent_id, token.access_token))
        return UserToken("new", "rt2", 999.0, "read")

    mc.set_token_refresher(_refresher)
    try:
        assert await mc._ensure_fresh_user_token(_server("puo"), "uA", "ag1") is True
        assert seen == [("puo", "uA", "ag1", "old")]
    finally:
        mc.set_token_refresher(None)


async def test_expired_no_refresh_token_proceeds_without_refresh(monkeypatch):
    """An expired token with no refresh token is not refreshable → proceed (degrades down)."""
    _fixed_now(monkeypatch, 300.0)
    monkeypatch.setattr(
        mc, "resolve_user_token", lambda *a, **k: UserToken("old", None, 200.0, "read")
    )
    called = []

    async def _refresher(*a):
        called.append(a)
        return UserToken("new", None, 999.0, "read")

    mc.set_token_refresher(_refresher)
    try:
        assert await mc._ensure_fresh_user_token(_server(), "uA", "ag1") is True
        assert called == []  # no refresh token → refresher never invoked
    finally:
        mc.set_token_refresher(None)


async def test_expired_no_refresher_proceeds(monkeypatch):
    """With no refresher wired, an expired token still proceeds (no crash, degrades down)."""
    _fixed_now(monkeypatch, 300.0)
    monkeypatch.setattr(
        mc, "resolve_user_token", lambda *a, **k: UserToken("old", "rt", 200.0, "read")
    )
    mc.set_token_refresher(None)
    assert await mc._ensure_fresh_user_token(_server(), "uA", "ag1") is True


async def test_genuine_refresh_failure_returns_false(monkeypatch):
    """Refresher returns None (revoked) → False, drives re-authorization."""
    _fixed_now(monkeypatch, 300.0)
    monkeypatch.setattr(
        mc, "resolve_user_token", lambda *a, **k: UserToken("old", "rt", 200.0, "read")
    )

    async def _refresher(*a):
        return None

    mc.set_token_refresher(_refresher)
    try:
        assert await mc._ensure_fresh_user_token(_server(), "uA", "ag1") is False
    finally:
        mc.set_token_refresher(None)


async def test_transient_refresh_error_keeps_token_and_proceeds(monkeypatch):
    """A raising refresher (transient) is contained: keep stale token, proceed."""
    _fixed_now(monkeypatch, 300.0)
    monkeypatch.setattr(
        mc, "resolve_user_token", lambda *a, **k: UserToken("old", "rt", 200.0, "read")
    )

    async def _refresher(*a):
        raise RuntimeError("token endpoint 503")

    mc.set_token_refresher(_refresher)
    try:
        assert await mc._ensure_fresh_user_token(_server(), "uA", "ag1") is True
    finally:
        mc.set_token_refresher(None)
