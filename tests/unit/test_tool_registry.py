import pytest

from fleetent import tool_registry


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate each test — snapshot and restore the registry."""
    before = dict(tool_registry._registry)
    yield
    tool_registry._registry.clear()
    tool_registry._registry.update(before)


def test_tool_decorator_registers_function():
    @tool_registry.tool
    def my_tool(x: str) -> str:
        """Do something."""
        return x

    assert "my_tool" in tool_registry._registry


def test_get_schemas_returns_openai_format():
    @tool_registry.tool
    def greet(name: str) -> str:
        """Greet someone."""
        return f"hello {name}"

    schemas = tool_registry.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "greet" in names
    schema = next(s for s in schemas if s["function"]["name"] == "greet")
    assert schema["type"] == "function"
    assert "parameters" in schema["function"]
    assert "name" in schema["function"]["parameters"]["properties"]


def test_dispatch_calls_function():
    @tool_registry.tool
    def add(a: str, b: str) -> str:
        """Add two numbers."""
        return str(int(a) + int(b))

    result = tool_registry.dispatch("add", '{"a": "2", "b": "3"}')
    assert result == "5"


def test_dispatch_unknown_tool_returns_error():
    result = tool_registry.dispatch("nonexistent", "{}")
    assert "unknown tool" in result


def test_schema_required_params():
    @tool_registry.tool
    def required_fn(required: str, optional: str = "default") -> str:
        """Test required vs optional."""
        return required

    schemas = tool_registry.get_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "required_fn")
    params = schema["function"]["parameters"]
    assert "required" in params["required"]
    assert "optional" not in params["required"]


def test_dispatch_with_allowed_tools_passes():
    @tool_registry.tool
    def _test_access_tool() -> str:
        """Test access control."""
        return "ok"

    result = tool_registry.dispatch("_test_access_tool", "{}", allowed_tools=["_test_access_tool"])
    assert result == "ok"


def test_dispatch_tool_not_in_allowed_tools_raises():
    with pytest.raises(PermissionError, match="not permitted"):
        tool_registry.dispatch("shell", "{}", allowed_tools=["github__*"])


def test_dispatch_without_allowed_tools_skips_check():
    # No allowed_tools = no check (backwards compat) — returns error string for unknown tool
    result = tool_registry.dispatch("nonexistent_tool_xyz", "{}")
    assert "unknown tool" in result


def test_dispatch_rejects_mcp_server_out_of_scope():
    with pytest.raises(PermissionError, match="not in agent scope"):
        tool_registry.dispatch("github__create", "{}", mcp_server_ids=["jira"], mcp_scope=5)


@pytest.mark.asyncio
async def test_dispatch_routes_in_scope_mcp_tool_with_agent_scope(monkeypatch):
    import fleetent.integrations.mcp.client as mcp_client

    captured: dict[str, object] = {}

    async def fake_call_tool(server_id, tool_name, args, scope=None):  # type: ignore[no-untyped-def]
        captured["server_id"] = server_id
        captured["tool_name"] = tool_name
        captured["args"] = args
        captured["scope"] = scope
        return "ok"

    monkeypatch.setattr(mcp_client, "call_tool", fake_call_tool)

    result = tool_registry.dispatch(
        "github__create", '{"x": 1}', mcp_server_ids=["github"], mcp_scope=5
    )
    out = await result  # type: ignore[misc]
    assert out == "ok"
    assert captured["server_id"] == "github"
    assert captured["tool_name"] == "create"
    assert captured["args"] == {"x": 1}
    assert captured["scope"] == 5


def test_dispatch_non_mcp_tool_ignores_mcp_scope():
    @tool_registry.tool
    def _scoped_builtin() -> str:
        """Builtin unaffected by mcp scope."""
        return "ok"

    result = tool_registry.dispatch("_scoped_builtin", "{}", mcp_server_ids=["jira"], mcp_scope=5)
    assert result == "ok"


def test_schema_type_mapping():
    @tool_registry.tool
    def typed_fn(s: str, n: int, f: float, b: bool) -> str:
        """Test type mapping."""
        return ""

    schemas = tool_registry.get_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "typed_fn")
    props = schema["function"]["parameters"]["properties"]
    assert props["s"]["type"] == "string"
    assert props["n"]["type"] == "integer"
    assert props["f"]["type"] == "number"
    assert props["b"]["type"] == "boolean"
