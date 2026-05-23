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
