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


@pytest.mark.asyncio
async def test_register_all_skips_unreachable_server(monkeypatch):
    """register_all should not raise when a server is unreachable."""
    import httpx

    async def fake_register_server(server: McpServerConfig) -> None:
        raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr(mcp_client, "_register_server", fake_register_server)

    bad_server = McpServerConfig(id="bad", url="http://localhost:19999", auth_type="none")
    # Should complete without raising even though server is unreachable
    await mcp_client.register_all([bad_server])


@pytest.mark.asyncio
async def test_register_tool_puts_in_registry():
    import fleetent.tools.registry as tr

    server = McpServerConfig(id="testsvr", url="http://localhost:9999", auth_type="none")
    tool_def = {
        "name": "do_thing",
        "description": "does a thing",
        "inputSchema": {"type": "object", "properties": {}},
    }

    mcp_client._register_tool_http(server, "testsvr__do_thing", tool_def)

    assert "testsvr__do_thing" in tr._registry
    fn, schema = tr._registry["testsvr__do_thing"]
    assert callable(fn)
    assert schema["function"]["name"] == "testsvr__do_thing"
    assert schema["function"]["description"] == "does a thing"


@pytest.mark.asyncio
async def test_register_tool_schema_format():
    """Registered MCP tool schema should be OpenAI function-call format."""
    import fleetent.tools.registry as tr

    server = McpServerConfig(id="linear", url="http://localhost:9998", auth_type="none")
    tool_def = {
        "name": "create_ticket",
        "description": "Create a Linear ticket",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
    }

    mcp_client._register_tool_http(server, "linear__create_ticket", tool_def)

    assert "linear__create_ticket" in tr._registry
    fn, schema = tr._registry["linear__create_ticket"]
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "linear__create_ticket"
    assert "parameters" in schema["function"]


@pytest.mark.asyncio
async def test_register_server_registers_tools_from_response(monkeypatch):
    """_register_server fetches tools/list and registers each tool."""
    import httpx
    import respx

    import fleetent.tools.registry as tr
    from fleetent.integrations.mcp.client import McpServerConfig, _register_server

    server = McpServerConfig(id="mysvr", url="http://mcp.test", auth_type="none")

    tools_response = {
        "result": {
            "tools": [
                {
                    "name": "do_thing",
                    "description": "does a thing",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ]
        }
    }

    with respx.mock:
        respx.post("http://mcp.test/").mock(return_value=httpx.Response(200, json=tools_response))
        await _register_server(server)

    assert "mysvr__do_thing" in tr._registry


@pytest.mark.asyncio
async def test_register_server_with_api_key_auth(monkeypatch):
    """_register_server sets Authorization header when auth_type=api_key."""
    import httpx
    import respx

    from fleetent.integrations.mcp.client import McpServerConfig, _register_server

    monkeypatch.setenv("MY_API_KEY", "secret-token")
    server = McpServerConfig(
        id="authsvr", url="http://auth.test", auth_type="api_key", api_key_env="MY_API_KEY"
    )

    captured_headers: list[dict] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured_headers.append(dict(request.headers))
        return httpx.Response(200, json={"result": {"tools": []}})

    with respx.mock:
        respx.post("http://auth.test/").mock(side_effect=capture)
        await _register_server(server)

    assert captured_headers[0].get("authorization") == "Bearer secret-token"


@pytest.mark.asyncio
async def test_call_tool_sends_jsonrpc_and_returns_result(monkeypatch):
    """call_tool posts tools/call and returns result field from response."""
    import httpx
    import respx

    import fleetent.integrations.mcp.client as mcp
    from fleetent.integrations.mcp.client import McpServerConfig

    server = McpServerConfig(id="callee", url="http://callee.test", auth_type="none")
    monkeypatch.setitem(mcp._server_registry, (None, "callee"), server)

    with respx.mock:
        respx.post("http://callee.test/").mock(
            return_value=httpx.Response(
                200,
                json={"result": {"content": [{"type": "text", "text": "42"}]}},
            )
        )
        result = await mcp.call_tool("callee", "compute", {"x": 1})

    assert result == "42"


@pytest.mark.asyncio
async def test_call_tool_unknown_server_raises():
    import fleetent.integrations.mcp.client as mcp

    with pytest.raises(KeyError, match="Unknown MCP server"):
        await mcp.call_tool("no_such_server", "tool", {})


@pytest.mark.asyncio
async def test_registry_keyed_by_scope(monkeypatch):
    """Same server_id under two scopes yields distinct registry entries."""
    import httpx
    import respx

    s_a = McpServerConfig(id="github", url="http://a.test", auth_type="none")
    s_b = McpServerConfig(id="github", url="http://b.test", auth_type="none")

    with respx.mock:
        respx.post("http://a.test/").mock(
            return_value=httpx.Response(200, json={"result": {"tools": []}})
        )
        respx.post("http://b.test/").mock(
            return_value=httpx.Response(200, json={"result": {"tools": []}})
        )
        await mcp_client.register_all([s_a], scope=5)
        await mcp_client.register_all([s_b], scope=7)

    assert mcp_client._server_registry[(5, "github")].url == "http://a.test"
    assert mcp_client._server_registry[(7, "github")].url == "http://b.test"


@pytest.mark.asyncio
async def test_call_tool_scope_selects_distinct_servers(monkeypatch):
    """Two scopes for one server_id route to their own url/credential."""
    import httpx
    import respx

    s_a = McpServerConfig(id="github", url="http://a.test", auth_type="none")
    s_b = McpServerConfig(id="github", url="http://b.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, (5, "github"), s_a)
    monkeypatch.setitem(mcp_client._server_registry, (7, "github"), s_b)

    with respx.mock:
        respx.post("http://a.test/").mock(
            return_value=httpx.Response(
                200, json={"result": {"content": [{"type": "text", "text": "A"}]}}
            )
        )
        respx.post("http://b.test/").mock(
            return_value=httpx.Response(
                200, json={"result": {"content": [{"type": "text", "text": "B"}]}}
            )
        )
        assert await mcp_client.call_tool("github", "t", {}, scope=5) == "A"
        assert await mcp_client.call_tool("github", "t", {}, scope=7) == "B"


@pytest.mark.asyncio
async def test_call_tool_unknown_scope_raises(monkeypatch):
    """A scope with no registered server_id is rejected, not silently global."""
    s_global = McpServerConfig(id="github", url="http://g.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, (None, "github"), s_global)

    with pytest.raises(KeyError, match="Unknown MCP server"):
        await mcp_client.call_tool("github", "t", {}, scope=5)
