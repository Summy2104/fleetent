"""Unit: the MCP chokepoint translates /workspace args to host paths for stdio servers.

A stdio MCP server is a host process whose mount namespace has no /workspace, so the
container path must be rewritten to the host bind-mount source before the call. http
servers (remote) and calls without a scope_key are left byte-identical.
"""

from __future__ import annotations

from fleetent.integrations.mcp import client as mc
from fleetent.integrations.mcp.client import HealthState, McpServerConfig
from fleetent.integrations.sandbox import manager


class _FakeSession:
    def __init__(self) -> None:
        self.received_args: object = None

    async def call_tool(self, name, args):
        self.received_args = args
        return object()  # opaque; _result_to_text is stubbed


def _wire(monkeypatch, server_id: str, transport: str) -> _FakeSession:
    server = McpServerConfig(id=server_id, transport=transport)
    server._health = HealthState.healthy
    fake = _FakeSession()
    monkeypatch.setitem(mc._server_registry, (None, server_id), server)
    monkeypatch.setitem(mc._active_sessions, (None, server_id), fake)
    monkeypatch.setattr(mc, "_result_to_text", lambda result: "ok")
    monkeypatch.setattr(mc, "_rewrite_result_paths", lambda *a, **k: "ok")
    return fake


async def test_stdio_args_translated_to_host_path(monkeypatch):
    fake = _wire(monkeypatch, "email", "stdio")
    await mc._call_via_session_inner(
        "email", "send_email", {"path": "/workspace/g/x.png"}, None, scope_key="s1"
    )
    expected = str(manager.host_workspace_dir("s1") / "g" / "x.png")
    assert fake.received_args == {"path": expected}


async def test_http_args_not_translated(monkeypatch):
    fake = _wire(monkeypatch, "jira", "http")
    await mc._call_via_session_inner(
        "jira", "search", {"path": "/workspace/g/x.png"}, None, scope_key="s1"
    )
    assert fake.received_args == {"path": "/workspace/g/x.png"}


async def test_stdio_without_scope_key_not_translated(monkeypatch):
    fake = _wire(monkeypatch, "email", "stdio")
    await mc._call_via_session_inner(
        "email", "send_email", {"path": "/workspace/g/x.png"}, None, scope_key=None
    )
    assert fake.received_args == {"path": "/workspace/g/x.png"}
