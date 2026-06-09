"""Unit tests for per-server MCP HTTP timeouts (mcp-per-server-timeout).

With the SDK transport the long-lived session is opened once: connect_timeout maps to the
SDK transport's `timeout`, call_timeout to its `sse_read_timeout`. Captures the kwargs
passed to streamablehttp_client via monkeypatch; no real I/O.
"""

import pytest

import fleetent.integrations.mcp.client as mc


class _BoomError(Exception):
    pass


def _capture_streamable_kwargs(monkeypatch) -> dict:
    """Patch streamablehttp_client to record its timeout kwargs then short-circuit."""
    captured: dict = {}

    def fake_client(url, *args, timeout=None, sse_read_timeout=None, **kwargs):
        captured["timeout"] = timeout
        captured["sse_read_timeout"] = sse_read_timeout
        raise _BoomError()

    monkeypatch.setattr(mc, "streamablehttp_client", fake_client)
    return captured


def test_config_timeout_defaults():
    s = mc.McpServerConfig(id="s")
    assert s.connect_timeout == 10.0
    assert s.call_timeout == 30.0


async def test_register_http_uses_connect_timeout(monkeypatch):
    server = mc.McpServerConfig(id="s", url="http://x", connect_timeout=5.0)
    captured = _capture_streamable_kwargs(monkeypatch)
    with pytest.raises(_BoomError):
        await mc._register_session_server(server)
    assert captured["timeout"] == 5.0


async def test_register_http_maps_call_timeout_to_sse_read(monkeypatch):
    server = mc.McpServerConfig(id="s", url="http://x", call_timeout=90.0)
    captured = _capture_streamable_kwargs(monkeypatch)
    with pytest.raises(_BoomError):
        await mc._register_session_server(server)
    assert captured["sse_read_timeout"] == 90.0


async def test_probe_http_uses_connect_timeout(monkeypatch):
    server = mc.McpServerConfig(id="s", url="http://x", connect_timeout=7.0)
    captured = _capture_streamable_kwargs(monkeypatch)
    # probe_server swallows the failure into a clean result; the kwargs are still captured.
    result = await mc.probe_server(server)
    assert result["connected"] is False
    assert captured["timeout"] == 7.0


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
