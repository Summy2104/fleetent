import pytest

import mini_agent.mcp_client as mcp_client
from mini_agent.mcp_client import McpServerConfig, _make_tool_name


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate each test — snapshot and restore the registry."""
    import mini_agent.tool_registry as tr

    before = dict(tr._registry)
    yield
    tr._registry.clear()
    tr._registry.update(before)


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
    import mini_agent.tool_registry as tr

    server = McpServerConfig(id="testsvr", url="http://localhost:9999", auth_type="none")
    tool_def = {
        "name": "do_thing",
        "description": "does a thing",
        "inputSchema": {"type": "object", "properties": {}},
    }

    mcp_client._register_tool(server, "testsvr__do_thing", tool_def)

    assert "testsvr__do_thing" in tr._registry
    fn, schema = tr._registry["testsvr__do_thing"]
    assert callable(fn)
    assert schema["function"]["name"] == "testsvr__do_thing"
    assert schema["function"]["description"] == "does a thing"


@pytest.mark.asyncio
async def test_register_tool_schema_format():
    """Registered MCP tool schema should be OpenAI function-call format."""
    import mini_agent.tool_registry as tr

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

    mcp_client._register_tool(server, "linear__create_ticket", tool_def)

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

    import mini_agent.tool_registry as tr
    from mini_agent.mcp_client import McpServerConfig, _register_server

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

    from mini_agent.mcp_client import McpServerConfig, _register_server

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

    import mini_agent.mcp_client as mcp
    from mini_agent.mcp_client import McpServerConfig

    server = McpServerConfig(id="callee", url="http://callee.test", auth_type="none")
    monkeypatch.setitem(mcp._server_registry, "callee", server)

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
    import mini_agent.mcp_client as mcp

    with pytest.raises(KeyError, match="Unknown MCP server"):
        await mcp.call_tool("no_such_server", "tool", {})
