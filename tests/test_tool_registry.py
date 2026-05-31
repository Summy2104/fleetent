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


# ── cancel-token out-of-band injection (AR19 D3) ─────────────────────────────


def test_dispatch_injects_token_into_opt_in_tool():
    from fleetent.cancellation import CancelToken

    received: dict[str, object] = {}

    @tool_registry.tool
    def opt_in_tool(x: str, cancel_token=None) -> str:
        """A tool that opts into receiving the token."""
        received["token"] = cancel_token
        return x

    token = CancelToken()
    result = tool_registry.dispatch("opt_in_tool", '{"x": "v"}', cancel_token=token)
    assert result == "v"
    assert received["token"] is token


def test_dispatch_does_not_inject_token_into_non_opt_in_tool():
    from fleetent.cancellation import CancelToken

    @tool_registry.tool
    def plain_tool(x: str) -> str:
        """A tool that does not declare cancel_token."""
        return x

    # Passing a token must not break or alter a tool that did not opt in.
    token = CancelToken()
    result = tool_registry.dispatch("plain_tool", '{"x": "v"}', cancel_token=token)
    assert result == "v"


def test_dispatch_without_token_passes_none_default_to_opt_in_tool():
    received: dict[str, object] = {}

    @tool_registry.tool
    def opt_in_tool2(x: str, cancel_token=None) -> str:
        """Opt-in tool dispatched without a token."""
        received["token"] = cancel_token
        return x

    result = tool_registry.dispatch("opt_in_tool2", '{"x": "v"}')
    assert result == "v"
    # No token supplied → the tool's own default (None) is used; nothing injected.
    assert received["token"] is None


def test_schema_excludes_cancel_token_param():
    @tool_registry.tool
    def schema_opt_in(x: str, cancel_token=None) -> str:
        """Opt-in tool — token must not leak into the LLM schema."""
        return x

    schemas = tool_registry.get_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "schema_opt_in")
    params = schema["function"]["parameters"]
    assert "cancel_token" not in params["properties"]
    assert "cancel_token" not in params["required"]
    assert "x" in params["properties"]


def test_schema_unaffected_for_tool_without_token():
    @tool_registry.tool
    def schema_plain(x: str, y: str = "d") -> str:
        """Tool without token — schema unchanged."""
        return x

    schemas = tool_registry.get_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "schema_plain")
    props = schema["function"]["parameters"]["properties"]
    assert set(props) == {"x", "y"}


def test_dispatch_injects_tool_context_into_opt_in_tool():
    from fleetent.tool_registry import ToolContext

    received: dict[str, object] = {}

    @tool_registry.tool
    def ctx_tool(x: str, tool_context=None) -> str:
        """A tool that opts into receiving the execution context."""
        received["ctx"] = tool_context
        return x

    ctx = ToolContext(agent_name="a", features={"code_execution": True}, session_id="s1")
    result = tool_registry.dispatch("ctx_tool", '{"x": "v"}', tool_context=ctx)
    assert result == "v"
    assert received["ctx"] is ctx


def test_dispatch_does_not_inject_context_into_non_opt_in_tool():
    from fleetent.tool_registry import ToolContext

    @tool_registry.tool
    def plain_ctx_tool(x: str) -> str:
        """A tool that does not declare tool_context."""
        return x

    ctx = ToolContext(agent_name="a", features={}, session_id="s")
    # Passing context must not break a tool that did not opt in.
    result = tool_registry.dispatch("plain_ctx_tool", '{"x": "v"}', tool_context=ctx)
    assert result == "v"


def test_dispatch_without_context_passes_none_to_opt_in_tool():
    received: dict[str, object] = {}

    @tool_registry.tool
    def ctx_tool2(x: str, tool_context=None) -> str:
        """Opt-in context tool dispatched without context."""
        received["ctx"] = tool_context
        return x

    result = tool_registry.dispatch("ctx_tool2", '{"x": "v"}')
    assert result == "v"
    assert received["ctx"] is None


def test_schema_excludes_tool_context_param():
    @tool_registry.tool
    def schema_ctx(x: str, tool_context=None) -> str:
        """Opt-in context tool — context must not leak into the LLM schema."""
        return x

    schemas = tool_registry.get_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "schema_ctx")
    params = schema["function"]["parameters"]
    assert "tool_context" not in params["properties"]
    assert "tool_context" not in params["required"]
    assert "x" in params["properties"]
