"""Integration tests for the MCP client's registry/tool wiring over the SDK transport.

All transports go through the official SDK ClientSession now, so these mock the SDK
transport + ClientSession (not the httpx wire) and assert the registry/tool/scope/probe
collaboration around that single seam.
"""

import contextlib
from types import SimpleNamespace
from typing import Any

import pytest

import fleetent.integrations.mcp.client as mcp_client
from fleetent.integrations.mcp.client import McpServerConfig, _make_tool_name


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate each test — snapshot and restore the tool + MCP registries."""
    import fleetent.tools.registry as tr

    before = dict(tr._registry)
    srv_before = dict(mcp_client._server_registry)
    sess_before = dict(mcp_client._active_sessions)
    yield
    tr._registry.clear()
    tr._registry.update(before)
    mcp_client._server_registry.clear()
    mcp_client._server_registry.update(srv_before)
    mcp_client._active_sessions.clear()
    mcp_client._active_sessions.update(sess_before)


def _obj(**kw: Any) -> SimpleNamespace:
    return SimpleNamespace(**kw)


def _tool(name: str, desc: str = "d") -> SimpleNamespace:
    return SimpleNamespace(
        name=name, description=desc, inputSchema={"type": "object", "properties": {}}
    )


class _FakeSession:
    """Minimal stand-in for mcp.ClientSession across all transports."""

    def __init__(self, tools: list[Any] | None = None, call_result: Any = None) -> None:
        self._tools = tools or []
        self._call_result = call_result

    async def initialize(self) -> Any:
        return SimpleNamespace(protocolVersion="2025-11-25", capabilities={})

    async def list_tools(self, cursor: str | None = None) -> Any:
        return SimpleNamespace(tools=self._tools, nextCursor=None)

    async def call_tool(self, name: str, args: dict, **kw: Any) -> Any:
        return self._call_result


def _install_sdk(
    monkeypatch,
    session: _FakeSession,
    *,
    capture_headers: list | None = None,
    transport_exc: Exception | None = None,
) -> None:
    """Patch the SDK transport + ClientSession the client imported at module top."""

    def fake_streamable(*a: Any, **k: Any) -> Any:
        if capture_headers is not None:
            capture_headers.append(k.get("headers"))
        if transport_exc is not None:
            raise transport_exc

        @contextlib.asynccontextmanager
        async def _cm():
            yield ("read", "write", None)

        return _cm()

    monkeypatch.setattr(mcp_client, "streamablehttp_client", fake_streamable)
    monkeypatch.setattr(mcp_client, "sse_client", fake_streamable)

    @contextlib.asynccontextmanager
    async def _session_cm(*a: Any, **k: Any):
        yield session

    monkeypatch.setattr(mcp_client, "ClientSession", lambda *a, **k: _session_cm())


# ── tool naming convention ────────────────────────────────────────────────────


def test_tool_naming_convention():
    assert _make_tool_name("linear", "create_ticket") == "linear__create_ticket"


def test_tool_naming_no_collision_with_local():
    assert _make_tool_name("my_server", "shell") == "my_server__shell"
    assert _make_tool_name("my_server", "shell") != "shell"


def test_tool_naming_double_underscore():
    name = _make_tool_name("github", "create_issue")
    assert "__" in name
    server_id, tool = name.split("__", 1)
    assert server_id == "github"
    assert tool == "create_issue"


# ── registration ──────────────────────────────────────────────────────────────


async def test_register_all_skips_unreachable_server(monkeypatch):
    """register_all should not raise when a server is unreachable."""
    import httpx

    async def fake_register_server(server: McpServerConfig, scope: int | None = None) -> None:
        raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr(mcp_client, "_register_server", fake_register_server)

    bad_server = McpServerConfig(id="bad", url="http://localhost:19999", auth_type="none")
    # Should complete without raising even though server is unreachable
    await mcp_client.register_all([bad_server])


async def test_register_tool_puts_in_registry():
    import fleetent.tools.registry as tr

    server = McpServerConfig(id="testsvr", url="http://localhost:9999", auth_type="none")
    mcp_client._register_tool(server, "testsvr__do_thing", _tool("do_thing", "does a thing"))

    assert "testsvr__do_thing" in tr._registry
    fn, schema = tr._registry["testsvr__do_thing"]
    assert callable(fn)
    assert schema["function"]["name"] == "testsvr__do_thing"
    assert schema["function"]["description"] == "does a thing"


async def test_register_tool_schema_format():
    """Registered MCP tool schema should be OpenAI function-call format."""
    import fleetent.tools.registry as tr

    server = McpServerConfig(id="linear", url="http://localhost:9998", auth_type="none")
    tool_def = _obj(
        name="create_ticket",
        description="Create a Linear ticket",
        inputSchema={
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
    )
    mcp_client._register_tool(server, "linear__create_ticket", tool_def)

    assert "linear__create_ticket" in tr._registry
    _fn, schema = tr._registry["linear__create_ticket"]
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "linear__create_ticket"
    assert "parameters" in schema["function"]


async def test_register_server_registers_tools_from_response(monkeypatch):
    """_register_server lists tools through the held SDK session and registers each."""
    import fleetent.tools.registry as tr
    from fleetent.integrations.mcp.client import _register_server

    _install_sdk(monkeypatch, _FakeSession(tools=[_tool("do_thing", "does a thing")]))
    server = McpServerConfig(id="mysvr", url="http://mcp.test", auth_type="none")
    await _register_server(server)

    assert "mysvr__do_thing" in tr._registry


async def test_register_server_with_api_key_auth(monkeypatch):
    """_register_server sets the Authorization header passed to the SDK transport."""
    from fleetent.integrations.mcp.client import _register_server

    monkeypatch.setenv("MY_API_KEY", "secret-token")
    server = McpServerConfig(
        id="authsvr", url="http://auth.test", auth_type="api_key", api_key_env="MY_API_KEY"
    )
    headers: list = []
    _install_sdk(monkeypatch, _FakeSession(tools=[]), capture_headers=headers)
    await _register_server(server)

    assert headers[0].get("Authorization") == "Bearer secret-token"


# ── call_tool ───────────────────────────────────────────────────────────────


async def test_call_tool_returns_normalized_result(monkeypatch):
    """call_tool dispatches through the held session and normalizes the result."""
    server = McpServerConfig(id="callee", url="http://callee.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, (None, "callee"), server)
    result = _obj(content=[_obj(type="text", text="42")], structuredContent=None, isError=False)
    monkeypatch.setitem(
        mcp_client._active_sessions, (None, "callee"), _FakeSession(call_result=result)
    )

    assert await mcp_client.call_tool("callee", "compute", {"x": 1}) == "42"


async def test_call_tool_unknown_server_raises():
    with pytest.raises(KeyError, match="Unknown MCP server"):
        await mcp_client.call_tool("no_such_server", "tool", {})


# ── (scope, server_id) keying ─────────────────────────────────────────────────


async def test_registry_keyed_by_scope(monkeypatch):
    """Same server_id under two scopes yields distinct registry entries."""
    _install_sdk(monkeypatch, _FakeSession(tools=[]))
    s_a = McpServerConfig(id="github", url="http://a.test", auth_type="none")
    s_b = McpServerConfig(id="github", url="http://b.test", auth_type="none")
    await mcp_client.register_all([s_a], scope=5)
    await mcp_client.register_all([s_b], scope=7)

    assert mcp_client._server_registry[(5, "github")].url == "http://a.test"
    assert mcp_client._server_registry[(7, "github")].url == "http://b.test"


async def test_call_tool_scope_selects_distinct_servers(monkeypatch):
    """Two scopes for one server_id route to their own held session."""
    s_a = McpServerConfig(id="github", url="http://a.test", auth_type="none")
    s_b = McpServerConfig(id="github", url="http://b.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, (5, "github"), s_a)
    monkeypatch.setitem(mcp_client._server_registry, (7, "github"), s_b)
    res_a = _obj(content=[_obj(type="text", text="A")], structuredContent=None, isError=False)
    res_b = _obj(content=[_obj(type="text", text="B")], structuredContent=None, isError=False)
    monkeypatch.setitem(mcp_client._active_sessions, (5, "github"), _FakeSession(call_result=res_a))
    monkeypatch.setitem(mcp_client._active_sessions, (7, "github"), _FakeSession(call_result=res_b))

    assert await mcp_client.call_tool("github", "t", {}, scope=5) == "A"
    assert await mcp_client.call_tool("github", "t", {}, scope=7) == "B"


async def test_call_tool_unknown_scope_raises(monkeypatch):
    """A scope with no registered server_id is rejected, not silently global."""
    s_global = McpServerConfig(id="github", url="http://g.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, (None, "github"), s_global)

    with pytest.raises(KeyError, match="Unknown MCP server"):
        await mcp_client.call_tool("github", "t", {}, scope=5)


# ── probe_server ──────────────────────────────────────────────────────────────


async def test_probe_server_http_success(monkeypatch):
    """probe_server connects, lists tools, returns connected + count without registering."""
    import fleetent.tools.registry as tr

    _install_sdk(monkeypatch, _FakeSession(tools=[_tool("a"), _tool("b")]))
    server = McpServerConfig(id="probe1", url="http://localhost:9999", auth_type="none")
    result = await mcp_client.probe_server(server)

    assert result["connected"] is True
    assert result["tool_count"] == 2
    assert {t["name"] for t in result["tools"]} == {"a", "b"}
    # probe must not pollute the global registry
    assert (None, "probe1") not in mcp_client._server_registry
    assert "probe1__a" not in tr._registry


async def test_probe_server_http_failure(monkeypatch):
    import httpx

    _install_sdk(monkeypatch, _FakeSession(), transport_exc=httpx.ConnectError("refused"))
    server = McpServerConfig(id="probe2", url="http://localhost:1", auth_type="none")
    result = await mcp_client.probe_server(server)

    assert result["connected"] is False
    assert "refused" in result["error"]


# ── unregister ────────────────────────────────────────────────────────────────


def test_unregister_server_removes_tools():
    import fleetent.tools.registry as tr

    server = McpServerConfig(id="gone", url="http://x", auth_type="none")
    mcp_client._register_tool(server, "gone__t1", _tool("t1"))
    mcp_client._register_tool(server, "gone__t2", _tool("t2"))
    mcp_client._server_registry[(None, "gone")] = server
    assert "gone__t1" in tr._registry

    mcp_client.unregister_server("gone")

    assert "gone__t1" not in tr._registry
    assert "gone__t2" not in tr._registry
    assert (None, "gone") not in mcp_client._server_registry


# ── header assembly ───────────────────────────────────────────────────────────


async def test_http_headers_includes_custom_headers():
    server = McpServerConfig(id="h", url="http://x", auth_type="none", headers={"X-API-Key": "k"})
    headers = await mcp_client._http_headers(server)
    assert headers["X-API-Key"] == "k"
