import pytest

from fleetent.tools import registry as tool_registry


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate each test — snapshot and restore the registry."""
    before = dict(tool_registry._registry)
    before_connectors = dict(tool_registry._connectors)
    yield
    tool_registry._registry.clear()
    tool_registry._registry.update(before)
    tool_registry._connectors.clear()
    tool_registry._connectors.update(before_connectors)


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

    async def fake_call_tool(server_id, tool_name, args, scope=None, **kw):  # type: ignore[no-untyped-def]
        captured["server_id"] = server_id
        captured["tool_name"] = tool_name
        captured["args"] = args
        captured["scope"] = scope
        captured["scope_key"] = kw.get("scope_key")
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


# ── cancel-token out-of-band injection (AR19 D3) ─────────────────────────────


def test_dispatch_injects_token_into_opt_in_tool():
    from fleetent.runtime.cancellation import CancelToken

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
    from fleetent.runtime.cancellation import CancelToken

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
    from fleetent.tools.registry import ToolContext

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


def test_tool_context_carries_conversation_address():
    """ToolContext exposes the authoritative current-conversation delivery address.

    send-file-to-conversation: send_file resolves its recipient from this address
    (channel -> channel, DM -> DM), the same address text replies use. Defaults to
    None so non-gateway run paths (standalone CLI / streaming) fall back gracefully.
    """
    from fleetent.tools.registry import ToolContext

    assert ToolContext().conversation_address is None
    addr = object()
    ctx = ToolContext(conversation_address=addr)
    assert ctx.conversation_address is addr


def test_dispatch_does_not_inject_context_into_non_opt_in_tool():
    from fleetent.tools.registry import ToolContext

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


# --- connector metadata (D1) ---


def test_tool_records_connector_metadata():
    @tool_registry.tool(connector="google-drive", scopes=["drive.readonly"])
    def gd_tool(query: str) -> str:
        """Search drive."""
        return query

    assert tool_registry.get_connector("gd_tool") == ("google-drive", ["drive.readonly"])


def test_get_connector_none_when_undeclared():
    @tool_registry.tool
    def plain_tool(x: str) -> str:
        """No connector."""
        return x

    assert tool_registry.get_connector("plain_tool") is None


def test_connector_scopes_not_in_schema():
    @tool_registry.tool(connector="github", scopes=["repo"])
    def gh_tool(q: str) -> str:
        """Search github."""
        return q

    schema = next(s for s in tool_registry.get_schemas() if s["function"]["name"] == "gh_tool")
    params = schema["function"]["parameters"]
    assert "connector" not in params["properties"]
    assert "scopes" not in params["properties"]
    assert set(params["properties"]) == {"q"}


# --- keyword-only hidden client excluded from schema (D4) ---


def test_keyword_only_client_not_in_schema():
    @tool_registry.tool
    def needs_client(query: str, *, client) -> str:
        """Tool with hidden client."""
        return query

    schema = next(s for s in tool_registry.get_schemas() if s["function"]["name"] == "needs_client")
    params = schema["function"]["parameters"]
    assert "client" not in params["properties"]
    assert "client" not in params["required"]
    assert "query" in params["properties"]


# --- connector credential injection at dispatch (D3/D5/D6) ---


def test_dispatch_injects_client_for_connector_tool(monkeypatch):
    from fleetent import connectors

    received: dict[str, object] = {}
    sentinel_client = object()

    @tool_registry.tool(connector="github", scopes=["repo"])
    def gh_search(q: str, *, client) -> str:
        """Search github."""
        received["client"] = client
        received["q"] = q
        return "results"

    def _provider(user_id, connector, scopes, agent_name=None):
        assert (user_id, connector, scopes) == ("u1", "github", ["repo"])
        return connectors.Credential(connector="github", client=sentinel_client)

    monkeypatch.setattr(connectors, "_provider", _provider)
    result = tool_registry.dispatch("gh_search", '{"q": "term"}', user_id="u1")
    assert result == "results"
    assert received["client"] is sentinel_client
    assert received["q"] == "term"


def test_dispatch_non_connector_tool_does_not_call_get_credential(monkeypatch):
    from fleetent import connectors

    called = {"v": False}

    def _boom(*a, **k):
        called["v"] = True
        raise AssertionError("get_credential must not be called for non-connector tools")

    monkeypatch.setattr(connectors, "get_credential", _boom)

    @tool_registry.tool
    def plain_no_conn(x: str) -> str:
        """No connector declared."""
        return x

    result = tool_registry.dispatch("plain_no_conn", '{"x": "v"}', user_id="u1")
    assert result == "v"
    assert called["v"] is False


def test_dispatch_short_circuits_on_needs_consent(monkeypatch):
    from fleetent import connectors

    ran = {"v": False}

    @tool_registry.tool(connector="google-drive", scopes=["drive"])
    def gd_search(q: str, *, client) -> str:
        """Search drive."""
        ran["v"] = True
        return "should not run"

    def _provider(user_id, connector, scopes, agent_name=None):
        return connectors.NeedsConsent(connector="google-drive", consent_url="https://auth/gd")

    monkeypatch.setattr(connectors, "_provider", _provider)
    result = tool_registry.dispatch("gd_search", '{"q": "x"}', user_id="u1")
    assert ran["v"] is False
    assert "https://auth/gd" in result
    assert "google-drive" in result


def test_dispatch_short_circuits_on_credential_error(monkeypatch):
    from fleetent import connectors

    ran = {"v": False}

    @tool_registry.tool(connector="google-drive", scopes=["drive"])
    def gd_refresh(q: str, *, client) -> str:
        """Search drive."""
        ran["v"] = True
        return "should not run"

    def _provider(user_id, connector, scopes, agent_name=None):
        return connectors.CredentialError(
            connector="google-drive",
            message="credential refresh failed",
            retryable=True,
            detail="refresh-secret",
        )

    monkeypatch.setattr(connectors, "_provider", _provider)
    result = tool_registry.dispatch("gd_refresh", '{"q": "x"}', user_id="u1")
    assert ran["v"] is False
    assert "temporarily unavailable" in result
    assert "refresh-secret" not in result


def test_dispatch_connector_tool_without_user_id_short_circuits(monkeypatch):
    ran = {"v": False}

    @tool_registry.tool(connector="github", scopes=["repo"])
    def gh_no_uid(q: str, *, client) -> str:
        """Search github."""
        ran["v"] = True
        return "x"

    # Default provider would never be consulted without user_id; degrade to consent.
    result = tool_registry.dispatch("gh_no_uid", '{"q": "x"}')
    assert ran["v"] is False
    assert "github" in result


def test_dispatch_does_not_leak_secret_in_result(monkeypatch):
    from fleetent import connectors

    secret = "ya29.TOP-SECRET-abc"

    @tool_registry.tool(connector="github", scopes=["repo"])
    def gh_echo(q: str, *, client) -> str:
        """Echo."""
        return f"ran with q={q}"

    def _provider(user_id, connector, scopes, agent_name=None):
        return connectors.Credential(connector="github", client=object(), secret=secret)

    monkeypatch.setattr(connectors, "_provider", _provider)
    result = tool_registry.dispatch("gh_echo", '{"q": "v"}', user_id="u1")
    assert secret not in result


def test_no_credential_in_trace(monkeypatch):
    """Full dispatch + eval_logger serialization carries no secret (D5 guard)."""
    from fleetent import connectors, eval_logger

    secret = "ya29.TRACE-LEAK-test"

    @tool_registry.tool(connector="github", scopes=["repo"])
    def gh_trace(q: str, *, client) -> str:
        """Echo for trace test."""
        return f"done: {q}"

    def _provider(user_id, connector, scopes, agent_name=None):
        return connectors.Credential(connector="github", client=object(), secret=secret)

    monkeypatch.setattr(connectors, "_provider", _provider)
    args_json = '{"q": "hello"}'
    result = tool_registry.dispatch("gh_trace", args_json, user_id="u1")

    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "gh_trace", "arguments": args_json},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": result},
    ]
    serialized = [eval_logger._serialize(m) for m in messages]
    import json as _json

    blob = _json.dumps(serialized)
    assert secret not in blob


# ── ToolContext outbound connectors (send-im-message-tool) ─────────────────────


def test_tool_context_carries_outbound_connectors() -> None:
    """ToolContext exposes outbound_connectors, defaulting to an empty dict."""
    from fleetent.tools.registry import ToolContext

    assert ToolContext().outbound_connectors == {}

    connector = object()
    ctx = ToolContext(outbound_connectors={"slack": connector})
    assert ctx.outbound_connectors["slack"] is connector
