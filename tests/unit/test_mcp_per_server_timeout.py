"""Unit tests for per-server MCP HTTP timeouts (mcp-per-server-timeout).

Captures the timeout passed to httpx.AsyncClient via monkeypatch; no real I/O.
"""

import pytest

import fleetent.integrations.mcp.client as mc


class _BoomError(Exception):
    pass


def _capture_async_client_timeout(monkeypatch) -> dict:
    """Patch httpx.AsyncClient to record the timeout kwarg then short-circuit."""
    captured: dict = {}

    def fake_client(*args, timeout=None, **kwargs):
        captured["timeout"] = timeout
        raise _BoomError()

    monkeypatch.setattr("httpx.AsyncClient", fake_client)
    return captured


def test_config_timeout_defaults():
    s = mc.McpServerConfig(id="s")
    assert s.connect_timeout == 10.0
    assert s.call_timeout == 30.0


async def test_register_http_uses_connect_timeout(monkeypatch):
    server = mc.McpServerConfig(id="s", url="http://x", connect_timeout=5.0)
    captured = _capture_async_client_timeout(monkeypatch)
    with pytest.raises(_BoomError):
        await mc._register_http_server(server)
    assert captured["timeout"] == 5.0


async def test_probe_http_uses_connect_timeout(monkeypatch):
    server = mc.McpServerConfig(id="s", url="http://x", connect_timeout=7.0)
    captured = _capture_async_client_timeout(monkeypatch)
    with pytest.raises(_BoomError):
        await mc._probe_http_tools(server)
    assert captured["timeout"] == 7.0


async def test_call_http_uses_call_timeout(monkeypatch):
    server = mc.McpServerConfig(id="s", url="http://x", call_timeout=90.0)
    monkeypatch.setitem(mc._server_registry, (None, "s"), server)
    captured = _capture_async_client_timeout(monkeypatch)
    with pytest.raises(_BoomError):
        await mc._call_http_tool("s", "t", {})
    assert captured["timeout"] == 90.0


# ── agent config: McpServerSettings carries the timeout fields ───────────────


def test_mcp_server_settings_timeout_defaults():
    from fleetent.config import McpServerSettings

    s = McpServerSettings(id="s")
    assert s.connect_timeout == 10.0
    assert s.call_timeout == 30.0


def test_mcp_server_settings_timeout_declared():
    from fleetent.config import McpServerSettings

    s = McpServerSettings(id="s", connect_timeout=5.0, call_timeout=120.0)
    assert s.connect_timeout == 5.0
    assert s.call_timeout == 120.0
