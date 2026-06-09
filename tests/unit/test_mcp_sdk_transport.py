"""Unit tests for the SDK-based unified MCP transport: held ClientSession registration,
single-path call, and lazy reconnect. Mocks the SDK ClientSession (not the httpx wire)."""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any

import pytest

import fleetent.integrations.mcp.client as mc
from fleetent.integrations.mcp.client import HealthState, McpServerConfig


def _tool(name: str, desc: str = "d") -> SimpleNamespace:
    return SimpleNamespace(
        name=name, description=desc, inputSchema={"type": "object", "properties": {}}
    )


class _FakeSession:
    """Minimal stand-in for mcp.ClientSession."""

    def __init__(self, tools: list[Any] | None = None, call_result: Any = None) -> None:
        self._tools = tools or []
        self._call_result = call_result
        self.calls: list[tuple[str, dict]] = []
        self.initialized = False
        self.call_exc: Exception | None = None

    async def initialize(self) -> Any:
        self.initialized = True
        return SimpleNamespace(protocolVersion="2025-11-25", capabilities={})

    async def list_tools(self, cursor: str | None = None) -> Any:
        return SimpleNamespace(tools=self._tools, nextCursor=None)

    async def call_tool(self, name: str, args: dict) -> Any:
        self.calls.append((name, args))
        if self.call_exc is not None:
            exc, self.call_exc = self.call_exc, None  # raise once
            raise exc
        return self._call_result or SimpleNamespace(
            content=[], structuredContent=None, isError=False
        )


@contextlib.asynccontextmanager
async def _fake_transport(*args: Any, **kwargs: Any):
    # All SDK clients yield a stream tuple; first two items are (read, write).
    yield ("read", "write", None)


def _install_fakes(monkeypatch, session: _FakeSession) -> None:
    """Patch the SDK transport + ClientSession the client module imported at top level."""
    monkeypatch.setattr(mc, "streamablehttp_client", lambda *a, **k: _fake_transport())
    monkeypatch.setattr(mc, "sse_client", lambda *a, **k: _fake_transport())
    monkeypatch.setattr(mc, "stdio_client", lambda *a, **k: _fake_transport())

    @contextlib.asynccontextmanager
    async def _session_cm(read, write, message_handler=None):
        yield session

    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _session_cm(*a, **k))


def _http_server(sid: str = "remote") -> McpServerConfig:
    return McpServerConfig(id=sid, transport="http", url="https://host/mcp")


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    monkeypatch.setattr(mc, "_server_registry", {})
    monkeypatch.setattr(mc, "_active_sessions", {})
    yield


# ── registration via held SDK session ─────────────────────────────────────────


async def test_register_http_stores_session_and_tools(monkeypatch):
    session = _FakeSession(tools=[_tool("search")])
    _install_fakes(monkeypatch, session)
    import fleetent.tools.registry as tr

    monkeypatch.setattr(tr, "_registry", {})

    await mc._register_session_server(_http_server("kb"), scope=None)

    assert (None, "kb") in mc._active_sessions
    assert "kb__search" in tr._registry


async def test_register_sse_uses_sse_client(monkeypatch):
    session = _FakeSession(tools=[_tool("t")])
    used = {"sse": False}

    def fake_sse(*a, **k):
        used["sse"] = True
        return _fake_transport()

    _install_fakes(monkeypatch, session)
    monkeypatch.setattr(mc, "sse_client", fake_sse)
    import fleetent.tools.registry as tr

    monkeypatch.setattr(tr, "_registry", {})
    s = McpServerConfig(id="x", transport="sse", url="https://host/sse")

    await mc._register_session_server(s, scope=None)
    assert used["sse"] is True


# ── unified call path + normalization ─────────────────────────────────────────


async def test_call_via_session_normalizes_result(monkeypatch):
    result = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="hello")],
        structuredContent=None,
        isError=False,
    )
    session = _FakeSession(tools=[_tool("echo")], call_result=result)
    _install_fakes(monkeypatch, session)
    import fleetent.tools.registry as tr

    monkeypatch.setattr(tr, "_registry", {})
    await mc._register_session_server(_http_server("srv"), scope=None)

    out = await mc.call_tool("srv", "echo", {"x": 1})
    assert "hello" in out
    assert session.calls == [("echo", {"x": 1})]


# ── lazy reconnect ─────────────────────────────────────────────────────────────


async def test_lazy_reconnect_on_disconnect_retries(monkeypatch):
    import httpx

    result = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")], structuredContent=None, isError=False
    )
    session = _FakeSession(tools=[_tool("t")], call_result=result)
    session.call_exc = httpx.ConnectError("boom")  # first call drops
    _install_fakes(monkeypatch, session)
    import fleetent.tools.registry as tr

    monkeypatch.setattr(tr, "_registry", {})
    await mc._register_session_server(_http_server("srv"), scope=None)

    out = await mc.call_tool("srv", "t", {})
    # first call raised disconnect → reopened → retry returned ok
    assert "ok" in out
    assert mc._server_registry[(None, "srv")]._health is HealthState.healthy


async def test_lazy_reconnect_reopen_fails_returns_degraded(monkeypatch):
    import httpx

    session = _FakeSession(tools=[_tool("t")])
    session.call_exc = httpx.ConnectError("boom")
    _install_fakes(monkeypatch, session)
    import fleetent.tools.registry as tr

    monkeypatch.setattr(tr, "_registry", {})
    await mc._register_session_server(_http_server("srv"), scope=None)

    # Make reopen fail by patching _open_session_for to raise after registration.
    async def _fail(*a, **k):
        raise httpx.ConnectError("still down")

    monkeypatch.setattr(mc, "_open_session_for", _fail)

    out = await mc.call_tool("srv", "t", {})
    assert "unavailable" in out.lower() or "不可用" in out
    assert mc._server_registry[(None, "srv")]._health is HealthState.unavailable
