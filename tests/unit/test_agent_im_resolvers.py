"""Agent-side IM identity/address resolvers via node loopback (agent-hosted-im)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from fleetent.im_gateway import access


class _Resp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:  # noqa: D401
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_agent_identity_resolver_calls_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, *, headers=None, json=None, timeout=None):  # noqa: ANN001, A002
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp({"user_id": "user-42", "tenant_id": "acme"})

    monkeypatch.setattr(httpx, "post", fake_post)

    resolver = access.AgentIdentityResolver(
        loopback_url="http://127.0.0.1:8790",
        tui_token="ma-agent-token",
        agent_name="support",
        tenant_id="acme",
    )
    user_id = resolver("support", "slack", "U1")

    assert user_id == "user-42"
    assert captured["url"] == "http://127.0.0.1:8790/agent/support/identity/resolve"
    assert captured["headers"]["Authorization"] == "Bearer ma-agent-token"
    assert captured["json"] == {"tenant_id": "acme", "channel": "slack", "platform_user_id": "U1"}


def test_agent_address_resolver_calls_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, *, headers=None, json=None, timeout=None):  # noqa: ANN001, A002
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp({"addresses": [{"platform": "slack", "platform_user_id": "U1"}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    resolver = access.AgentAddressResolver(
        loopback_url="http://127.0.0.1:8790",
        tui_token="ma-agent-token",
        agent_name="support",
    )
    addrs = resolver.resolve("user-42")

    assert addrs == [{"platform": "slack", "platform_user_id": "U1"}]
    assert captured["url"] == "http://127.0.0.1:8790/agent/support/identity/addresses"
    assert captured["headers"]["Authorization"] == "Bearer ma-agent-token"
    assert captured["json"] == {"user_id": "user-42"}


def test_agent_link_confirmer_calls_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, *, headers=None, json=None, timeout=None):  # noqa: ANN001, A002
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp({"status": "linked"})

    monkeypatch.setattr(httpx, "post", fake_post)

    confirmer = access.AgentLinkConfirmer(
        loopback_url="http://127.0.0.1:8790",
        tui_token="ma-agent-token",
        agent_name="support",
    )
    ok, _detail = confirmer.confirm("slack", "U1", "abc123")

    assert ok is True
    assert captured["url"] == "http://127.0.0.1:8790/agent/support/link-confirm"
    assert captured["headers"]["Authorization"] == "Bearer ma-agent-token"
    assert captured["json"] == {"platform": "slack", "platform_user_id": "U1", "code": "abc123"}


def test_link_confirmer_seam_default_none() -> None:
    """No confirmer wired (standalone) → confirm_link returns None (not applicable)."""
    access.set_im_link_confirmer(None)
    assert access.confirm_link("slack", "U1", "abc123") is None


def test_link_confirmer_seam_injected() -> None:
    access.set_im_link_confirmer(lambda platform, puid, code: (True, "ok"))
    try:
        assert access.confirm_link("slack", "U1", "abc123") == (True, "ok")
    finally:
        access.set_im_link_confirmer(None)


def test_address_resolver_seam_default_none() -> None:
    """set_im_address_resolver seam mirrors set_im_identity_resolver; default resolves empty."""
    access.set_im_address_resolver(None)
    assert access.resolve_addresses("user-42") == []


def test_address_resolver_seam_injected() -> None:
    access.set_im_address_resolver(lambda uid: [{"platform": "telegram", "platform_user_id": "9"}])
    try:
        assert access.resolve_addresses("user-42") == [
            {"platform": "telegram", "platform_user_id": "9"}
        ]
    finally:
        access.set_im_address_resolver(None)
