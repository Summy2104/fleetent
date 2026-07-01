"""Unit: MCP client normalizes the per-user triple's agent identity.

managed IM turns don't thread `agent_name` into `loop.run()`, so the tool context's agent
name arrives empty and the OAuth/credential triple would key on `agent_id=''` (breaking
per-agent isolation and per-agent client_secret resolution). `call_tool` MUST fill the
identity from the process's single active agent when the caller supplies none, while
leaving an explicit identity untouched (managed-oauth-agent-identity).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fleetent.integrations.mcp import client as mcp_client


def test_effective_agent_id_fills_from_active_agent(monkeypatch):
    monkeypatch.setattr(
        "fleetent.agent_config.active_agent", lambda: SimpleNamespace(name="bi-intern")
    )
    assert mcp_client._effective_agent_id(None) == "bi-intern"
    assert mcp_client._effective_agent_id("") == "bi-intern"


def test_effective_agent_id_keeps_explicit_identity(monkeypatch):
    monkeypatch.setattr(
        "fleetent.agent_config.active_agent", lambda: SimpleNamespace(name="bi-intern")
    )
    # An explicit identity is never overridden by the active agent.
    assert mcp_client._effective_agent_id("other") == "other"


def test_effective_agent_id_none_when_no_single_active_agent(monkeypatch):
    monkeypatch.setattr("fleetent.agent_config.active_agent", lambda: None)
    assert mcp_client._effective_agent_id(None) is None
    assert mcp_client._effective_agent_id("") is None


async def test_call_tool_normalizes_empty_agent_id(monkeypatch):
    monkeypatch.setattr(
        "fleetent.agent_config.active_agent", lambda: SimpleNamespace(name="bi-intern")
    )
    monkeypatch.setitem(
        mcp_client._server_registry, (None, "google-drive"), SimpleNamespace(id="google-drive")
    )
    captured: dict[str, object] = {}

    async def fake_via_session(*args, **kwargs):
        captured["agent_id"] = kwargs.get("agent_id")
        return "ok"

    monkeypatch.setattr(mcp_client, "_call_via_session", AsyncMock(side_effect=fake_via_session))

    await mcp_client.call_tool("google-drive", "list", {}, user_id="U1", agent_id=None)
    assert captured["agent_id"] == "bi-intern"


async def test_call_tool_keeps_explicit_agent_id(monkeypatch):
    monkeypatch.setattr(
        "fleetent.agent_config.active_agent", lambda: SimpleNamespace(name="bi-intern")
    )
    monkeypatch.setitem(
        mcp_client._server_registry, (None, "google-drive"), SimpleNamespace(id="google-drive")
    )
    captured: dict[str, object] = {}

    async def fake_via_session(*args, **kwargs):
        captured["agent_id"] = kwargs.get("agent_id")
        return "ok"

    monkeypatch.setattr(mcp_client, "_call_via_session", AsyncMock(side_effect=fake_via_session))

    await mcp_client.call_tool("google-drive", "list", {}, user_id="U1", agent_id="explicit")
    assert captured["agent_id"] == "explicit"
