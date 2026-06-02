import json

import httpx
import pytest

import fleetent.integrations.mcp.client as mcp_client
from fleetent.integrations.mcp.client import McpServerConfig, _make_tool_name


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate each test — snapshot and restore the registry."""
    import fleetent.tool_registry as tr

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
    import fleetent.tool_registry as tr

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
    import fleetent.tool_registry as tr

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


def _make_streamable_handler(
    tools: list[dict] | None = None,
    session_id: str | None = None,
    captured: list[httpx.Request] | None = None,
    tool_result_text: str = "",
):
    """Build a respx side_effect that routes JSON-RPC requests by method.

    initialize -> empty result (+ optional Mcp-Session-Id header)
    tools/list -> the given tools
    tools/call -> a text content result
    notifications/initialized -> 202 (no body)
    """
    import httpx as _httpx

    def handler(request: _httpx.Request) -> _httpx.Response:
        if captured is not None:
            captured.append(request)
        payload = json.loads(request.content)
        method = payload.get("method")
        req_id = payload.get("id")
        if method == "notifications/initialized":
            return _httpx.Response(202)
        if method == "initialize":
            headers = {}
            if session_id is not None:
                headers["Mcp-Session-Id"] = session_id
            return _httpx.Response(
                200,
                headers=headers,
                json={"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "x"}},
            )
        if method == "tools/list":
            return _httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools or []}},
            )
        if method == "tools/call":
            return _httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": tool_result_text}]},
                },
            )
        return _httpx.Response(400)

    return handler


@pytest.mark.asyncio
async def test_register_server_registers_tools_from_response(monkeypatch):
    """_register_server does initialize then tools/list and registers each tool."""
    import respx

    import fleetent.tool_registry as tr
    from fleetent.integrations.mcp.client import McpServerConfig, _register_server

    server = McpServerConfig(id="mysvr", url="http://mcp.test", auth_type="none")
    tools = [{"name": "do_thing", "description": "does a thing", "inputSchema": {"type": "object"}}]
    captured: list = []

    with respx.mock:
        respx.post("http://mcp.test/").mock(
            side_effect=_make_streamable_handler(tools=tools, captured=captured)
        )
        await _register_server(server)

    assert "mysvr__do_thing" in tr._registry
    methods = [json.loads(r.content).get("method") for r in captured]
    # initialize must precede tools/list
    assert methods.index("initialize") < methods.index("tools/list")


@pytest.mark.asyncio
async def test_register_server_saves_session_id(monkeypatch):
    """initialize response with Mcp-Session-Id is saved and echoed on tools/list."""
    import respx

    from fleetent.mcp_client import McpServerConfig, _register_server

    server = McpServerConfig(id="sesssvr", url="http://sess.test", auth_type="none")
    captured: list = []

    with respx.mock:
        respx.post("http://sess.test/").mock(
            side_effect=_make_streamable_handler(
                tools=[{"name": "t", "inputSchema": {"type": "object"}}],
                session_id="sess-abc",
                captured=captured,
            )
        )
        await _register_server(server)

    assert server.session_id == "sess-abc"
    tools_list_reqs = [r for r in captured if json.loads(r.content).get("method") == "tools/list"]
    assert tools_list_reqs[0].headers.get("mcp-session-id") == "sess-abc"


@pytest.mark.asyncio
async def test_register_server_sends_accept_header(monkeypatch):
    """Every request declares Accept: application/json, text/event-stream."""
    import respx

    from fleetent.mcp_client import McpServerConfig, _register_server

    server = McpServerConfig(id="acc", url="http://acc.test", auth_type="none")
    captured: list = []

    with respx.mock:
        respx.post("http://acc.test/").mock(
            side_effect=_make_streamable_handler(tools=[], captured=captured)
        )
        await _register_server(server)

    accept = captured[0].headers.get("accept", "")
    assert "application/json" in accept
    assert "text/event-stream" in accept


@pytest.mark.asyncio
async def test_register_server_no_session_id_stays_none(monkeypatch):
    """initialize without Mcp-Session-Id leaves session_id None; registration succeeds."""
    import respx

    import fleetent.tool_registry as tr
    from fleetent.mcp_client import McpServerConfig, _register_server

    server = McpServerConfig(id="nosess", url="http://nosess.test", auth_type="none")
    captured: list = []

    with respx.mock:
        respx.post("http://nosess.test/").mock(
            side_effect=_make_streamable_handler(
                tools=[{"name": "t", "inputSchema": {"type": "object"}}],
                session_id=None,
                captured=captured,
            )
        )
        await _register_server(server)

    assert server.session_id is None
    assert "nosess__t" in tr._registry
    for r in captured:
        assert "mcp-session-id" not in {k.lower() for k in r.headers}


@pytest.mark.asyncio
async def test_register_server_with_api_key_auth(monkeypatch):
    """_register_server sets Authorization header when auth_type=api_key."""
    import respx

    from fleetent.integrations.mcp.client import McpServerConfig, _register_server

    monkeypatch.setenv("MY_API_KEY", "secret-token")
    server = McpServerConfig(
        id="authsvr", url="http://auth.test", auth_type="api_key", api_key_env="MY_API_KEY"
    )

    captured: list = []

    with respx.mock:
        respx.post("http://auth.test/").mock(
            side_effect=_make_streamable_handler(tools=[], captured=captured)
        )
        await _register_server(server)

    assert captured[0].headers.get("authorization") == "Bearer secret-token"


@pytest.mark.asyncio
async def test_call_tool_sends_jsonrpc_and_returns_result(monkeypatch):
    """call_tool posts tools/call and returns result field from response."""
    import httpx
    import respx

    import fleetent.integrations.mcp.client as mcp
    from fleetent.integrations.mcp.client import McpServerConfig

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
    import fleetent.integrations.mcp.client as mcp

    with pytest.raises(KeyError, match="Unknown MCP server"):
        await mcp.call_tool("no_such_server", "tool", {})


# --- Streamable HTTP: tools/call JSON + SSE responses ---


@pytest.mark.asyncio
async def test_call_tool_sse_response(monkeypatch):
    """tools/call with text/event-stream response is parsed via SSE extraction."""
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import McpServerConfig

    server = McpServerConfig(id="ssesvr", url="http://sse.test", auth_type="none")
    monkeypatch.setitem(mcp._server_registry, "ssesvr", server)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        req_id = payload["id"]
        body = (
            f"event: message\n"
            f'data: {{"jsonrpc": "2.0", "id": {req_id}, '
            f'"result": {{"content": [{{"type": "text", "text": "from-sse"}}]}}}}\n\n'
        )
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)

    with respx.mock:
        respx.post("http://sse.test/").mock(side_effect=handler)
        result = await mcp.call_tool("ssesvr", "compute", {"x": 1})

    assert result == "from-sse"


@pytest.mark.asyncio
async def test_call_tool_echoes_session_id(monkeypatch):
    """tools/call echoes the server's stored Mcp-Session-Id."""
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import McpServerConfig

    server = McpServerConfig(id="echo", url="http://echo.test", auth_type="none")
    server.session_id = "sess-xyz"
    monkeypatch.setitem(mcp._server_registry, "echo", server)

    captured: list = []

    with respx.mock:
        respx.post("http://echo.test/").mock(
            side_effect=_make_streamable_handler(captured=captured, tool_result_text="ok")
        )
        result = await mcp.call_tool("echo", "t", {})

    assert result == "ok"
    assert captured[0].headers.get("mcp-session-id") == "sess-xyz"


@pytest.mark.asyncio
async def test_call_tool_uses_increasing_request_id(monkeypatch):
    """Consecutive tools/call requests use distinct, increasing JSON-RPC ids."""
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import McpServerConfig

    server = McpServerConfig(id="inc", url="http://inc.test", auth_type="none")
    monkeypatch.setitem(mcp._server_registry, "inc", server)

    captured: list = []

    with respx.mock:
        respx.post("http://inc.test/").mock(
            side_effect=_make_streamable_handler(captured=captured, tool_result_text="ok")
        )
        await mcp.call_tool("inc", "t", {})
        await mcp.call_tool("inc", "t", {})

    ids = [json.loads(r.content)["id"] for r in captured]
    assert ids[0] < ids[1]


# --- Streamable HTTP: dispatch routing ---


@pytest.mark.asyncio
async def test_register_server_http_routes_to_http_impl(monkeypatch):
    """_register_server dispatches transport=http to _register_http_server."""
    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import McpServerConfig, _register_server

    called: list[str] = []

    async def fake_http(server: McpServerConfig) -> None:
        called.append("http")

    monkeypatch.setattr(mcp, "_register_http_server", fake_http)
    await _register_server(McpServerConfig(id="h", url="http://h.test", transport="http"))
    assert called == ["http"]


@pytest.mark.asyncio
async def test_register_server_stdio_routes_to_stdio_impl(monkeypatch):
    """_register_server dispatches transport=stdio to _register_stdio_server (unchanged)."""
    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import McpServerConfig, _register_server

    called: list[str] = []

    async def fake_stdio(server: McpServerConfig) -> None:
        called.append("stdio")

    monkeypatch.setattr(mcp, "_register_stdio_server", fake_stdio)
    await _register_server(McpServerConfig(id="s", transport="stdio", command="x"))
    assert called == ["stdio"]


@pytest.mark.asyncio
async def test_call_tool_http_routes_to_http_impl(monkeypatch):
    """call_tool dispatches http server to _call_http_tool."""
    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import McpServerConfig

    server = McpServerConfig(id="rh", url="http://rh.test", transport="http")
    monkeypatch.setitem(mcp._server_registry, "rh", server)

    called: list[str] = []

    async def fake_call(server_id: str, tool_name: str, args: dict) -> str:
        called.append("http")
        return "ok"

    monkeypatch.setattr(mcp, "_call_http_tool", fake_call)
    assert await mcp.call_tool("rh", "t", {}) == "ok"
    assert called == ["http"]


@pytest.mark.asyncio
async def test_call_tool_stdio_routes_to_stdio_impl(monkeypatch):
    """call_tool dispatches stdio server to _call_stdio_tool (unchanged)."""
    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import McpServerConfig

    server = McpServerConfig(id="rs", transport="stdio", command="x")
    monkeypatch.setitem(mcp._server_registry, "rs", server)

    called: list[str] = []

    async def fake_call(server_id: str, tool_name: str, args: dict) -> str:
        called.append("stdio")
        return "ok"

    monkeypatch.setattr(mcp, "_call_stdio_tool", fake_call)
    assert await mcp.call_tool("rs", "t", {}) == "ok"
    assert called == ["stdio"]


# --- Streamable HTTP: connection-failure degradation via register_all ---


@pytest.mark.asyncio
async def test_register_all_degrades_on_initialize_failure(monkeypatch):
    """One http server unreachable at initialize must not block the other's registration."""
    import respx

    import fleetent.mcp_client as mcp
    import fleetent.tool_registry as tr
    from fleetent.mcp_client import McpServerConfig

    bad = McpServerConfig(id="bad", url="http://bad.test", auth_type="none")
    good = McpServerConfig(id="good", url="http://good.test", auth_type="none")

    with respx.mock:
        respx.post("http://bad.test/").mock(side_effect=httpx.ConnectError("unreachable"))
        respx.post("http://good.test/").mock(
            side_effect=_make_streamable_handler(
                tools=[{"name": "ok_tool", "inputSchema": {"type": "object"}}]
            )
        )
        await mcp.register_all([bad, good])

    assert "good__ok_tool" in tr._registry
    assert not any(k.startswith("bad__") for k in tr._registry)


# --- Streamable HTTP: SSE parsing (_extract_jsonrpc_from_sse) ---


def test_extract_jsonrpc_from_sse_single_event():
    from fleetent.mcp_client import _extract_jsonrpc_from_sse

    body = 'event: message\ndata: {"jsonrpc": "2.0", "id": 5, "result": {"ok": true}}\n\n'
    obj = _extract_jsonrpc_from_sse(body, 5)
    assert obj["id"] == 5
    assert obj["result"] == {"ok": True}


def test_extract_jsonrpc_from_sse_matches_request_id():
    from fleetent.mcp_client import _extract_jsonrpc_from_sse

    body = (
        'data: {"jsonrpc": "2.0", "id": 1, "result": {"v": "other"}}\n\n'
        'data: {"jsonrpc": "2.0", "id": 7, "result": {"v": "mine"}}\n\n'
    )
    obj = _extract_jsonrpc_from_sse(body, 7)
    assert obj["result"] == {"v": "mine"}


def test_extract_jsonrpc_from_sse_multiline_data():
    from fleetent.mcp_client import _extract_jsonrpc_from_sse

    body = 'data: {"jsonrpc": "2.0",\ndata: "id": 3, "result": {"v": 1}}\n\n'
    obj = _extract_jsonrpc_from_sse(body, 3)
    assert obj["id"] == 3
    assert obj["result"] == {"v": 1}


def test_extract_jsonrpc_from_sse_ignores_comment_lines():
    from fleetent.mcp_client import _extract_jsonrpc_from_sse

    body = (
        ": this is a comment / keep-alive\n"
        'data: {"jsonrpc": "2.0", "id": 9, "result": {"v": 1}}\n\n'
    )
    obj = _extract_jsonrpc_from_sse(body, 9)
    assert obj["id"] == 9


def test_extract_jsonrpc_from_sse_ignores_non_matching_events():
    from fleetent.mcp_client import _extract_jsonrpc_from_sse

    body = (
        'data: {"jsonrpc": "2.0", "method": "notifications/progress", "params": {}}\n\n'
        'data: {"jsonrpc": "2.0", "id": 2, "result": {"v": "mine"}}\n\n'
    )
    obj = _extract_jsonrpc_from_sse(body, 2)
    assert obj["result"] == {"v": "mine"}


def test_extract_jsonrpc_from_sse_no_match_raises():
    from fleetent.mcp_client import _extract_jsonrpc_from_sse

    body = 'data: {"jsonrpc": "2.0", "id": 1, "result": {}}\n\n'
    with pytest.raises(ValueError):
        _extract_jsonrpc_from_sse(body, 99)


# --- Streamable HTTP: per-server session id + monotonic request id ---


def test_server_config_session_id_defaults_none():
    server = McpServerConfig(id="s1", url="http://s1.test")
    assert server.session_id is None


def test_next_request_id_is_monotonic_per_server():
    from fleetent.mcp_client import _next_request_id

    server = McpServerConfig(id="s2", url="http://s2.test")
    first = _next_request_id(server)
    second = _next_request_id(server)
    third = _next_request_id(server)
    assert first < second < third


def test_next_request_id_isolated_between_servers():
    from fleetent.mcp_client import _next_request_id

    a = McpServerConfig(id="a", url="http://a.test")
    b = McpServerConfig(id="b", url="http://b.test")
    a1 = _next_request_id(a)
    a2 = _next_request_id(a)
    b1 = _next_request_id(b)
    # b has its own counter, unaffected by a's two advances
    assert b1 == a1
    assert a2 == a1 + 1


# --- MCP2: session lifecycle helpers (open / reuse / expire) ---


def test_session_expire_clears_session_id():
    from fleetent.mcp_client import _expire_session

    server = McpServerConfig(id="exp", url="http://exp.test")
    server.session_id = "sess-old"
    _expire_session(server)
    assert server.session_id is None


def test_session_reuse_echoes_session_id_when_present():
    """_base_headers (reuse semantics) includes Mcp-Session-Id when set."""
    server = McpServerConfig(id="reuse", url="http://reuse.test")
    server.session_id = "sess-1"
    headers = mcp_client._base_headers(server)
    assert headers["Mcp-Session-Id"] == "sess-1"


def test_session_reuse_omits_session_id_when_absent():
    server = McpServerConfig(id="reuse2", url="http://reuse2.test")
    assert server.session_id is None
    headers = mcp_client._base_headers(server)
    assert "Mcp-Session-Id" not in headers


@pytest.mark.asyncio
async def test_open_session_writes_session_id_from_initialize(monkeypatch):
    """_open_session sends initialize and stores the Mcp-Session-Id from the response."""
    import respx

    server = McpServerConfig(id="open", url="http://open.test", auth_type="none")
    captured: list = []

    import httpx as _httpx

    async with _httpx.AsyncClient(timeout=10.0) as client:
        with respx.mock:
            respx.post("http://open.test/").mock(
                side_effect=_make_streamable_handler(session_id="sess-new", captured=captured)
            )
            await mcp_client._open_session(client, server)

    assert server.session_id == "sess-new"
    methods = [json.loads(r.content).get("method") for r in captured]
    assert "initialize" in methods
    assert "notifications/initialized" in methods


# --- MCP2: session expiry transparent rebuild (tools/call) ---


def _make_session_expiry_handler(
    *,
    expire_times: int,
    new_session_id: str,
    captured: list[httpx.Request],
    expiry_status: int = 404,
    tool_result_text: str = "ok",
):
    """Handler that returns `expire_status` for the first `expire_times` tools/call requests
    (those carrying any Mcp-Session-Id), then serves a normal result. initialize assigns
    `new_session_id`.
    """
    import httpx as _httpx

    state = {"expired_seen": 0}

    def handler(request: _httpx.Request) -> _httpx.Response:
        captured.append(request)
        payload = json.loads(request.content)
        method = payload.get("method")
        req_id = payload.get("id")
        if method == "notifications/initialized":
            return _httpx.Response(202)
        if method == "initialize":
            return _httpx.Response(
                200,
                headers={"Mcp-Session-Id": new_session_id},
                json={"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "x"}},
            )
        if method in ("tools/call", "tools/list"):
            if state["expired_seen"] < expire_times:
                state["expired_seen"] += 1
                return _httpx.Response(expiry_status)
            if method == "tools/list":
                return _httpx.Response(
                    200, json={"jsonrpc": "2.0", "id": req_id, "result": {"tools": []}}
                )
            return _httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": tool_result_text}]},
                },
            )
        return _httpx.Response(400)

    return handler


@pytest.mark.asyncio
async def test_call_tool_404_triggers_rebuild_and_retries(monkeypatch):
    """tools/call hitting 404 expires the session, re-initializes, and retries once."""
    import respx

    server = McpServerConfig(id="rb", url="http://rb.test", auth_type="none")
    server.session_id = "sess-stale"
    monkeypatch.setitem(mcp_client._server_registry, "rb", server)

    captured: list = []

    with respx.mock:
        respx.post("http://rb.test/").mock(
            side_effect=_make_session_expiry_handler(
                expire_times=1, new_session_id="sess-fresh", captured=captured
            )
        )
        result = await mcp_client.call_tool("rb", "compute", {"x": 1})

    assert result == "ok"
    assert server.session_id == "sess-fresh"
    methods = [json.loads(r.content).get("method") for r in captured]
    assert "initialize" in methods
    # final tools/call carried the fresh session id
    tool_calls = [r for r in captured if json.loads(r.content).get("method") == "tools/call"]
    assert tool_calls[-1].headers.get("mcp-session-id") == "sess-fresh"


@pytest.mark.asyncio
async def test_register_tools_list_404_triggers_rebuild(monkeypatch):
    """tools/list during registration hitting 404 triggers rebuild and completes."""
    import respx

    import fleetent.tool_registry as tr

    server = McpServerConfig(id="rblist", url="http://rblist.test", auth_type="none")
    captured: list = []

    import httpx as _httpx

    state = {"list_seen": 0}

    def handler(request: _httpx.Request) -> _httpx.Response:
        captured.append(request)
        payload = json.loads(request.content)
        method = payload.get("method")
        req_id = payload.get("id")
        if method == "notifications/initialized":
            return _httpx.Response(202)
        if method == "initialize":
            return _httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess-list"},
                json={"jsonrpc": "2.0", "id": req_id, "result": {}},
            )
        if method == "tools/list":
            if state["list_seen"] == 0:
                state["list_seen"] += 1
                return _httpx.Response(404)
            return _httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": [{"name": "t", "inputSchema": {"type": "object"}}]},
                },
            )
        return _httpx.Response(400)

    with respx.mock:
        respx.post("http://rblist.test/").mock(side_effect=handler)
        await mcp_client._register_server(server)

    assert "rblist__t" in tr._registry


@pytest.mark.asyncio
async def test_rebuild_at_most_once_second_404_raises(monkeypatch):
    """Two consecutive 404s: the retry's 404 is not rebuilt again, error propagates."""
    import respx

    server = McpServerConfig(id="loop", url="http://loop.test", auth_type="none")
    server.session_id = "sess-loop"
    monkeypatch.setitem(mcp_client._server_registry, "loop", server)

    captured: list = []

    with respx.mock:
        respx.post("http://loop.test/").mock(
            side_effect=_make_session_expiry_handler(
                expire_times=2, new_session_id="sess-loop2", captured=captured
            )
        )
        with pytest.raises(httpx.HTTPStatusError):
            await mcp_client.call_tool("loop", "compute", {})

    # initialize attempted exactly once (one rebuild), not repeatedly
    methods = [json.loads(r.content).get("method") for r in captured]
    assert methods.count("initialize") == 1


@pytest.mark.asyncio
async def test_register_tools_list_at_most_one_rebuild(monkeypatch):
    """tools/list path: two 404s also rebuild at most once, then propagate."""
    import respx

    server = McpServerConfig(id="loop2", url="http://loop2.test", auth_type="none")
    captured: list = []

    import httpx as _httpx

    def handler(request: _httpx.Request) -> _httpx.Response:
        captured.append(request)
        payload = json.loads(request.content)
        method = payload.get("method")
        req_id = payload.get("id")
        if method == "notifications/initialized":
            return _httpx.Response(202)
        if method == "initialize":
            return _httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess-x"},
                json={"jsonrpc": "2.0", "id": req_id, "result": {}},
            )
        if method == "tools/list":
            return _httpx.Response(404)
        return _httpx.Response(400)

    with respx.mock:
        respx.post("http://loop2.test/").mock(side_effect=handler)
        with pytest.raises(httpx.HTTPStatusError):
            await mcp_client._register_server(server)

    methods = [json.loads(r.content).get("method") for r in captured]
    assert methods.count("initialize") == 2  # original handshake + one rebuild


@pytest.mark.asyncio
async def test_auth_401_does_not_trigger_rebuild(monkeypatch):
    """401 is an auth error: no expire, no re-initialize, error propagates."""
    import respx

    server = McpServerConfig(id="auth401", url="http://auth401.test", auth_type="none")
    server.session_id = "sess-keep"
    monkeypatch.setitem(mcp_client._server_registry, "auth401", server)

    captured: list = []

    import httpx as _httpx

    def handler(request: _httpx.Request) -> _httpx.Response:
        captured.append(request)
        payload = json.loads(request.content)
        method = payload.get("method")
        if method == "tools/call":
            return _httpx.Response(401)
        return _httpx.Response(400)

    with respx.mock:
        respx.post("http://auth401.test/").mock(side_effect=handler)
        with pytest.raises(httpx.HTTPStatusError):
            await mcp_client.call_tool("auth401", "compute", {})

    methods = [json.loads(r.content).get("method") for r in captured]
    assert "initialize" not in methods
    assert server.session_id == "sess-keep"


@pytest.mark.asyncio
async def test_auth_403_does_not_trigger_rebuild(monkeypatch):
    """403 is an auth error: no rebuild, session preserved."""
    import respx

    server = McpServerConfig(id="auth403", url="http://auth403.test", auth_type="none")
    server.session_id = "sess-keep3"
    monkeypatch.setitem(mcp_client._server_registry, "auth403", server)

    import httpx as _httpx

    def handler(request: _httpx.Request) -> _httpx.Response:
        return _httpx.Response(403)

    with respx.mock:
        respx.post("http://auth403.test/").mock(side_effect=handler)
        with pytest.raises(httpx.HTTPStatusError):
            await mcp_client.call_tool("auth403", "compute", {})

    assert server.session_id == "sess-keep3"


# --- MCP2: close() sends DELETE for active HTTP sessions ---


@pytest.mark.asyncio
async def test_close_sends_delete_for_active_http_session(monkeypatch):
    """close() sends DELETE with Mcp-Session-Id for http servers holding a session id."""
    import respx

    server = McpServerConfig(id="del", url="http://del.test", auth_type="none")
    server.session_id = "sess-del"
    monkeypatch.setattr(mcp_client, "_server_registry", {"del": server})
    monkeypatch.setattr(mcp_client, "_exit_stack", None)

    captured: list = []

    import httpx as _httpx

    def handler(request: _httpx.Request) -> _httpx.Response:
        captured.append(request)
        return _httpx.Response(200)

    with respx.mock:
        respx.delete("http://del.test/").mock(side_effect=handler)
        await mcp_client.close()

    assert len(captured) == 1
    assert captured[0].headers.get("mcp-session-id") == "sess-del"
    assert server.session_id is None


@pytest.mark.asyncio
async def test_close_no_delete_when_no_session_id(monkeypatch):
    """close() does not send DELETE for http servers without a session id."""
    import respx

    server = McpServerConfig(id="nodel", url="http://nodel.test", auth_type="none")
    assert server.session_id is None
    monkeypatch.setattr(mcp_client, "_server_registry", {"nodel": server})
    monkeypatch.setattr(mcp_client, "_exit_stack", None)

    route = respx.delete("http://nodel.test/")
    with respx.mock:
        respx.delete("http://nodel.test/").mock(return_value=httpx.Response(200))
        await mcp_client.close()

    assert not route.called


@pytest.mark.asyncio
async def test_close_delete_failure_does_not_raise(monkeypatch):
    """DELETE failure during close() is swallowed (best-effort); session id still cleared."""
    import respx

    server = McpServerConfig(id="delfail", url="http://delfail.test", auth_type="none")
    server.session_id = "sess-fail"
    monkeypatch.setattr(mcp_client, "_server_registry", {"delfail": server})
    monkeypatch.setattr(mcp_client, "_exit_stack", None)

    with respx.mock:
        respx.delete("http://delfail.test/").mock(side_effect=httpx.ConnectError("down"))
        await mcp_client.close()  # must not raise

    assert server.session_id is None


@pytest.mark.asyncio
async def test_close_skips_stdio_servers(monkeypatch):
    """close() does not attempt DELETE against stdio servers."""
    import respx

    stdio_server = McpServerConfig(id="std", transport="stdio", command="x")
    stdio_server.session_id = "should-not-matter"
    monkeypatch.setattr(mcp_client, "_server_registry", {"std": stdio_server})
    monkeypatch.setattr(mcp_client, "_exit_stack", None)

    with respx.mock:
        # No routes registered; any HTTP call would raise. close() must not make one.
        await mcp_client.close()


# === MCP5: OAuth2 authentication ===========================================


def _token_handler(
    captured: list | None = None,
    access_token: str = "tok-1",
    expires_in: int | None = 3600,
    refresh_token: str | None = None,
    status: int = 200,
    error: str | None = None,
):
    """Build a respx side_effect for an OAuth2 token endpoint (client_credentials)."""
    import httpx as _httpx

    def handler(request: _httpx.Request) -> _httpx.Response:
        if captured is not None:
            captured.append(request)
        if error is not None or status >= 400:
            body: dict = {}
            if error is not None:
                body["error"] = error
            return _httpx.Response(status, json=body)
        body = {"access_token": access_token, "token_type": "Bearer"}
        if expires_in is not None:
            body["expires_in"] = expires_in
        if refresh_token is not None:
            body["refresh_token"] = refresh_token
        return _httpx.Response(200, json=body)

    return handler


def _oauth_server(server_id: str = "osvr", url: str = "http://o.test") -> McpServerConfig:
    return McpServerConfig(
        id=server_id,
        url=url,
        auth_type="oauth2",
        token_url="http://auth.test/token",
        client_id="cid",
        client_secret_env="OSVR_SECRET",
    )


# --- 2. config fields ---


def test_oauth2_config_fields_defaults():
    """McpServerConfig exposes OAuth2 fields with empty defaults."""
    s = McpServerConfig(id="x")
    assert s.token_url == ""
    assert s.client_id == ""
    assert s.client_secret_env == ""
    assert s.scope == ""


def test_oauth2_config_fields_set():
    s = McpServerConfig(
        id="x",
        auth_type="oauth2",
        token_url="http://auth.test/token",
        client_id="cid",
        client_secret_env="SECRET_ENV",
        scope="mcp.read",
    )
    assert s.auth_type == "oauth2"
    assert s.token_url == "http://auth.test/token"
    assert s.client_id == "cid"
    assert s.client_secret_env == "SECRET_ENV"
    assert s.scope == "mcp.read"


# --- 3. token store (per-server isolated, injectable) ---


def test_token_store_per_server_isolation(monkeypatch):
    from fleetent.mcp_client import _InMemoryTokenStore

    store_a = _InMemoryTokenStore()
    store_b = _InMemoryTokenStore()
    store_a.set("a", access_token="ta", expires_at=100.0, refresh_token=None)
    assert store_a.get("a") is not None
    assert store_a.get("a").access_token == "ta"
    assert store_b.get("a") is None  # different store, isolated


def test_token_store_reset(monkeypatch):
    from fleetent.mcp_client import _InMemoryTokenStore

    store = _InMemoryTokenStore()
    store.set("a", access_token="ta", expires_at=100.0, refresh_token=None)
    store.clear("a")
    assert store.get("a") is None


def test_token_store_not_module_global():
    """The default token store is held per-server-instance, not a module-level dict."""
    s1 = _oauth_server("s1")
    s2 = _oauth_server("s2")
    assert s1._token_store is not s2._token_store


# --- 4. client_credentials fetch + Bearer attach ---


@pytest.mark.asyncio
async def test_oauth2_fetches_token_and_attaches_bearer(monkeypatch):
    import respx

    from fleetent.mcp_client import _register_server

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server()
    captured_mcp: list = []
    captured_tok: list = []

    with respx.mock:
        respx.post("http://auth.test/token").mock(
            side_effect=_token_handler(captured=captured_tok, access_token="ACCESS-1")
        )
        respx.post("http://o.test/").mock(
            side_effect=_make_streamable_handler(tools=[], captured=captured_mcp)
        )
        await _register_server(server)

    # token endpoint hit with client_credentials grant
    assert len(captured_tok) >= 1
    tok_body = captured_tok[0].content.decode()
    assert "grant_type=client_credentials" in tok_body
    assert "client_id=cid" in tok_body
    assert "client_secret=shh" in tok_body
    # MCP request carries the access token as Bearer
    assert captured_mcp[0].headers.get("authorization") == "Bearer ACCESS-1"


@pytest.mark.asyncio
async def test_oauth2_includes_scope_when_set(monkeypatch):
    import respx

    from fleetent.mcp_client import _register_server

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server()
    server.scope = "mcp.read mcp.write"
    captured_tok: list = []

    with respx.mock:
        respx.post("http://auth.test/token").mock(side_effect=_token_handler(captured=captured_tok))
        respx.post("http://o.test/").mock(side_effect=_make_streamable_handler(tools=[]))
        await _register_server(server)

    assert "scope=" in captured_tok[0].content.decode()


@pytest.mark.asyncio
async def test_none_and_api_key_unaffected_no_token_call(monkeypatch):
    """none/api_key servers never hit a token endpoint (no oauth behavior leak)."""
    import respx

    from fleetent.mcp_client import _register_server

    server = McpServerConfig(id="plain", url="http://plain.test", auth_type="none")
    with respx.mock:
        route = respx.post("http://auth.test/token").mock(side_effect=_token_handler())
        respx.post("http://plain.test/").mock(side_effect=_make_streamable_handler(tools=[]))
        await _register_server(server)
    assert not route.called


# --- 5. auto refresh ---


@pytest.mark.asyncio
async def test_oauth2_refreshes_when_expired(monkeypatch):
    """An expired cached token triggers a re-fetch via client_credentials on next resolve."""
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import _resolve_oauth_token

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server()
    clock = {"now": 1000.0}
    monkeypatch.setattr(mcp, "_now", lambda: clock["now"])
    captured_tok: list = []

    with respx.mock:
        respx.post("http://auth.test/token").mock(
            side_effect=_token_handler(captured=captured_tok, access_token="A", expires_in=100)
        )
        t1 = await _resolve_oauth_token(server)
        assert t1 == "A"
        # advance past expiry (incl. safety margin)
        clock["now"] = 1000.0 + 100 + 10
        respx.post("http://auth.test/token").mock(
            side_effect=_token_handler(captured=captured_tok, access_token="B", expires_in=100)
        )
        t2 = await _resolve_oauth_token(server)
        assert t2 == "B"
    assert len(captured_tok) == 2


@pytest.mark.asyncio
async def test_oauth2_cached_token_reused_when_valid(monkeypatch):
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import _resolve_oauth_token

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server()
    monkeypatch.setattr(mcp, "_now", lambda: 1000.0)
    captured_tok: list = []

    with respx.mock:
        respx.post("http://auth.test/token").mock(
            side_effect=_token_handler(captured=captured_tok, access_token="A", expires_in=3600)
        )
        await _resolve_oauth_token(server)
        await _resolve_oauth_token(server)
    assert len(captured_tok) == 1


@pytest.mark.asyncio
async def test_oauth2_missing_refresh_token_is_normal(monkeypatch):
    """client_credentials response with no refresh_token is normal; re-fetch on expiry."""
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import _resolve_oauth_token

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server()
    clock = {"now": 0.0}
    monkeypatch.setattr(mcp, "_now", lambda: clock["now"])

    with respx.mock:
        respx.post("http://auth.test/token").mock(
            side_effect=_token_handler(access_token="A", expires_in=10, refresh_token=None)
        )
        await _resolve_oauth_token(server)
        clock["now"] = 100.0
        respx.post("http://auth.test/token").mock(
            side_effect=_token_handler(access_token="C", expires_in=10)
        )
        t = await _resolve_oauth_token(server)
    assert t == "C"  # refetched, not failed for missing refresh_token


@pytest.mark.asyncio
async def test_oauth2_no_expires_in_uses_conservative_ttl(monkeypatch):
    """Missing expires_in yields a bounded TTL (token still usable immediately)."""
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import _resolve_oauth_token

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server()
    monkeypatch.setattr(mcp, "_now", lambda: 0.0)

    with respx.mock:
        respx.post("http://auth.test/token").mock(
            side_effect=_token_handler(access_token="A", expires_in=None)
        )
        t = await _resolve_oauth_token(server)
    assert t == "A"
    cached = server._token_store.get(server.id)
    assert cached is not None
    assert cached.expires_at > 0.0  # a finite, future expiry was set


@pytest.mark.asyncio
async def test_oauth2_concurrent_resolve_single_token_call(monkeypatch):
    """Concurrent resolves on an expired token coalesce into one token fetch (D9)."""
    import asyncio

    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import _resolve_oauth_token

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server()
    monkeypatch.setattr(mcp, "_now", lambda: 0.0)
    captured_tok: list = []

    async def slow_handler(request):
        import httpx as _httpx

        captured_tok.append(request)
        await asyncio.sleep(0.02)
        return _httpx.Response(
            200, json={"access_token": "A", "expires_in": 3600, "token_type": "Bearer"}
        )

    with respx.mock:
        respx.post("http://auth.test/token").mock(side_effect=slow_handler)
        results = await asyncio.gather(*[_resolve_oauth_token(server) for _ in range(5)])

    assert all(r == "A" for r in results)
    assert len(captured_tok) == 1


@pytest.mark.asyncio
async def test_oauth2_per_server_lock_isolated(monkeypatch):
    """Different servers hold their own lock; both fetch independently."""
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import _resolve_oauth_token

    monkeypatch.setenv("OSVR_SECRET", "shh")
    monkeypatch.setenv("OTHER_SECRET", "shh2")
    s1 = _oauth_server("s1", "http://s1.test")
    s2 = McpServerConfig(
        id="s2",
        url="http://s2.test",
        auth_type="oauth2",
        token_url="http://auth2.test/token",
        client_id="cid2",
        client_secret_env="OTHER_SECRET",
    )
    monkeypatch.setattr(mcp, "_now", lambda: 0.0)

    with respx.mock:
        respx.post("http://auth.test/token").mock(side_effect=_token_handler(access_token="A1"))
        respx.post("http://auth2.test/token").mock(side_effect=_token_handler(access_token="A2"))
        t1 = await _resolve_oauth_token(s1)
        t2 = await _resolve_oauth_token(s2)
    assert t1 == "A1"
    assert t2 == "A2"
    assert s1._refresh_lock is not s2._refresh_lock


# --- 6. auth failure: sticky unavailable ---


@pytest.mark.asyncio
async def test_oauth2_invalid_client_marks_unavailable(monkeypatch):
    """401/invalid_client sets sticky auth-unavailable and surfaces re-auth guidance."""
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import OAuthAuthUnavailableError, _resolve_oauth_token

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server()
    monkeypatch.setattr(mcp, "_now", lambda: 0.0)

    with respx.mock:
        route = respx.post("http://auth.test/token").mock(
            side_effect=_token_handler(status=401, error="invalid_client")
        )
        with pytest.raises(OAuthAuthUnavailableError) as exc:
            await _resolve_oauth_token(server)
        assert (
            "re" in str(exc.value).lower() or "授权" in str(exc.value) or "凭据" in str(exc.value)
        )
        # second resolve must not hit the endpoint again (sticky, no retry)
        with pytest.raises(OAuthAuthUnavailableError):
            await _resolve_oauth_token(server)
    assert route.call_count == 1
    assert server._auth_unavailable is True


@pytest.mark.asyncio
async def test_oauth2_transient_5xx_not_sticky(monkeypatch):
    """5xx is transient: not sticky; next resolve can succeed."""
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import _resolve_oauth_token

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server()
    monkeypatch.setattr(mcp, "_now", lambda: 0.0)

    with respx.mock:
        respx.post("http://auth.test/token").mock(side_effect=_token_handler(status=503))
        with pytest.raises(httpx.HTTPStatusError):
            await _resolve_oauth_token(server)
        assert server._auth_unavailable is False
        respx.post("http://auth.test/token").mock(side_effect=_token_handler(access_token="OK"))
        t = await _resolve_oauth_token(server)
    assert t == "OK"


@pytest.mark.asyncio
async def test_oauth2_transient_network_error_not_sticky(monkeypatch):
    import respx

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import _resolve_oauth_token

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server()
    monkeypatch.setattr(mcp, "_now", lambda: 0.0)

    with respx.mock:
        respx.post("http://auth.test/token").mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(httpx.ConnectError):
            await _resolve_oauth_token(server)
    assert server._auth_unavailable is False


def test_oauth2_recovery_clears_sticky_on_reregister(monkeypatch):
    """Re-registration / config reload clears the sticky auth-unavailable flag."""
    from fleetent.mcp_client import _clear_oauth_auth_state

    server = _oauth_server()
    server._auth_unavailable = True
    _clear_oauth_auth_state(server)
    assert server._auth_unavailable is False


@pytest.mark.asyncio
async def test_oauth2_unavailable_short_circuits_tool_call(monkeypatch):
    """A tool call on an auth-unavailable oauth2 server returns an error result, no HTTP."""
    import respx

    import fleetent.mcp_client as mcp

    monkeypatch.setenv("OSVR_SECRET", "shh")
    server = _oauth_server("callee", "http://callee.test")
    server._auth_unavailable = True
    monkeypatch.setitem(mcp._server_registry, "callee", server)

    with respx.mock:
        tok = respx.post("http://auth.test/token").mock(side_effect=_token_handler())
        mcpr = respx.post("http://callee.test/").mock(side_effect=_make_streamable_handler())
        result = await mcp.call_tool("callee", "do", {})
    assert not tok.called
    assert not mcpr.called
    assert "authentication" in result.lower() or "认证" in result or "auth" in result.lower()


# --- 7. config example ---


def test_mcp_yaml_example_oauth2_entry_loads():
    """The oauth2 example in config/mcp.yaml.example constructs a valid McpServerConfig."""
    from pathlib import Path

    import yaml

    raw = yaml.safe_load(Path("config/mcp.yaml.example").read_text())
    oauth_entries = [s for s in raw["servers"] if s.get("auth_type") == "oauth2"]
    assert oauth_entries, "expected an oauth2 example server"
    s = McpServerConfig(**oauth_entries[0])
    assert s.auth_type == "oauth2"
    assert s.token_url
    assert s.client_id
    assert s.client_secret_env


# === MCP3: connection health checking & reconnect =========================
#
# Health states (D2): per-server, isolated, default healthy, resettable.
# D1: connection-level disconnects map to AR5 mcp_disconnect by reading
# CLASSIFICATION_TABLE directly (NOT via classify()).
# D5: degraded/unavailable -> tool calls return an "unavailable" string.
# D7: HTTP 404 is session expiry (MCP2), never a connection disconnect (MCP3).


def test_health_state_defaults_to_healthy():
    server = McpServerConfig(id="h1", url="http://h1.test")
    assert mcp_client.get_health(server) is mcp_client.HealthState.healthy


def test_health_state_is_injectable_and_resettable():
    server = McpServerConfig(id="h2", url="http://h2.test")
    mcp_client.set_health(server, mcp_client.HealthState.degraded)
    assert mcp_client.get_health(server) is mcp_client.HealthState.degraded
    mcp_client.reset_health(server)
    assert mcp_client.get_health(server) is mcp_client.HealthState.healthy


def test_health_state_isolated_per_server():
    a = McpServerConfig(id="a", url="http://a.test")
    b = McpServerConfig(id="b", url="http://b.test")
    mcp_client.set_health(a, mcp_client.HealthState.unavailable)
    assert mcp_client.get_health(a) is mcp_client.HealthState.unavailable
    assert mcp_client.get_health(b) is mcp_client.HealthState.healthy


def test_health_state_not_module_level_global():
    """Health must live on the server instance, not a module-level mutable dict."""
    assert not hasattr(mcp_client, "_health_states")
    assert not hasattr(mcp_client, "_HEALTH")


# --- D1: disconnect exception -> mcp_disconnect via CLASSIFICATION_TABLE ---


def test_disconnect_error_recognized_httpx():
    assert mcp_client._is_disconnect_error(httpx.ConnectError("down"))
    assert mcp_client._is_disconnect_error(httpx.ConnectTimeout("slow"))
    assert mcp_client._is_disconnect_error(httpx.ReadError("eof"))


def test_disconnect_error_rejects_http_status_error():
    """An HTTPStatusError (e.g. 404/401) is NOT a connection-level disconnect."""
    req = httpx.Request("POST", "http://x.test/")
    resp = httpx.Response(404, request=req)
    exc = httpx.HTTPStatusError("nf", request=req, response=resp)
    assert not mcp_client._is_disconnect_error(exc)


def test_disconnect_maps_to_mcp_disconnect_reading_table_directly():
    """D1: mcp_client decides mcp_disconnect itself and reads CLASSIFICATION_TABLE,
    yielding should_retry=True — without going through classify()."""
    from fleetent.error_classifier import ErrorCategory

    classification = mcp_client._disconnect_classification()
    assert classification.category is ErrorCategory.mcp_disconnect
    assert classification.should_retry is True


def test_guard_classify_of_disconnect_is_unknown_not_mcp_disconnect():
    """Guard: classify() does NOT recognize disconnect exceptions; it returns unknown.
    This proves MCP3 cannot rely on classify() for the mcp_disconnect mapping (D1)."""
    from fleetent.error_classifier import ErrorCategory, classify

    for exc in (
        httpx.ConnectError("down"),
        httpx.ConnectTimeout("slow"),
        httpx.ReadError("eof"),
    ):
        result = classify(exc)
        assert result.category is ErrorCategory.unknown
        assert result.category is not ErrorCategory.mcp_disconnect


@pytest.mark.asyncio
async def test_http_disconnect_turns_server_degraded(monkeypatch):
    """A connection-level disconnect on a tool call transitions the server to degraded."""
    import respx

    server = McpServerConfig(id="dc", url="http://dc.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "dc", server)
    monkeypatch.setattr(mcp_client, "_schedule_reconnect", lambda s: None)

    with respx.mock:
        respx.post("http://dc.test/").mock(side_effect=httpx.ConnectError("down"))
        result = await mcp_client.call_tool("dc", "compute", {})

    assert mcp_client.get_health(server) is mcp_client.HealthState.degraded
    assert "unavailable" in result.lower() or "不可用" in result


@pytest.mark.asyncio
async def test_stdio_disconnect_turns_server_degraded(monkeypatch):
    """A dead/missing stdio session is a connection disconnect -> degraded + unavailable text."""
    from unittest.mock import AsyncMock

    server = McpServerConfig(id="sd", transport="stdio", command="x")
    monkeypatch.setitem(mcp_client._server_registry, "sd", server)
    monkeypatch.setattr(mcp_client, "_schedule_reconnect", lambda s: None)

    session = AsyncMock()
    session.call_tool = AsyncMock(side_effect=ConnectionError("broken pipe / EOF"))
    monkeypatch.setitem(mcp_client._active_sessions, "sd", session)

    result = await mcp_client.call_tool("sd", "do", {})

    assert mcp_client.get_health(server) is mcp_client.HealthState.degraded
    assert "unavailable" in result.lower() or "不可用" in result


# --- D5: degraded/unavailable tool calls short-circuit to unavailable text ---


@pytest.mark.asyncio
async def test_degraded_tool_call_returns_unavailable_without_network(monkeypatch):
    """A degraded server's tool call returns the unavailable string and makes no request."""
    import respx

    server = McpServerConfig(id="deg", url="http://deg.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "deg", server)
    mcp_client.set_health(server, mcp_client.HealthState.degraded)

    route = respx.post("http://deg.test/")
    with respx.mock:
        respx.post("http://deg.test/").mock(return_value=httpx.Response(200))
        result = await mcp_client.call_tool("deg", "compute", {})

    assert not route.called
    assert "unavailable" in result.lower() or "不可用" in result


@pytest.mark.asyncio
async def test_unavailable_tool_call_returns_unavailable_without_network(monkeypatch):
    import respx

    server = McpServerConfig(id="un", url="http://un.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "un", server)
    mcp_client.set_health(server, mcp_client.HealthState.unavailable)

    route = respx.post("http://un.test/")
    with respx.mock:
        respx.post("http://un.test/").mock(return_value=httpx.Response(200))
        result = await mcp_client.call_tool("un", "compute", {})

    assert not route.called
    assert "unavailable" in result.lower() or "不可用" in result


@pytest.mark.asyncio
async def test_degraded_does_not_affect_other_healthy_server(monkeypatch):
    """One server degraded does not block tool calls on another healthy server."""
    import respx

    bad = McpServerConfig(id="bad", url="http://bad.test", auth_type="none")
    good = McpServerConfig(id="good", url="http://good.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "bad", bad)
    monkeypatch.setitem(mcp_client._server_registry, "good", good)
    mcp_client.set_health(bad, mcp_client.HealthState.degraded)

    with respx.mock:
        respx.post("http://good.test/").mock(
            side_effect=_make_streamable_handler(tool_result_text="good-ok")
        )
        result = await mcp_client.call_tool("good", "compute", {})

    assert result == "good-ok"
    assert mcp_client.get_health(good) is mcp_client.HealthState.healthy


# --- D7: 404 session expiry is NOT an MCP3 disconnect (stays MCP2) ---


@pytest.mark.asyncio
async def test_404_session_expiry_does_not_degrade(monkeypatch):
    """HTTP 404 triggers MCP2 rebuild and must NOT mark the server degraded (D7)."""
    import respx

    server = McpServerConfig(id="d7", url="http://d7.test", auth_type="none")
    server.session_id = "sess-stale"
    monkeypatch.setitem(mcp_client._server_registry, "d7", server)

    with respx.mock:
        respx.post("http://d7.test/").mock(
            side_effect=_make_session_expiry_handler(
                expire_times=1, new_session_id="sess-fresh", captured=[]
            )
        )
        result = await mcp_client.call_tool("d7", "compute", {"x": 1})

    assert result == "ok"
    assert mcp_client.get_health(server) is mcp_client.HealthState.healthy


# --- D4: exponential backoff sequence ---


def test_backoff_sequence_doubles_and_caps():
    """1 -> 2 -> 4 -> ... capped at the configured ceiling, base/cap injectable."""
    seq = [mcp_client._backoff_delay(n, base=1.0, cap=60.0) for n in range(8)]
    assert seq[:7] == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0]
    assert seq[7] == 60.0  # stays capped


def test_backoff_sequence_short_injectable_values():
    seq = [mcp_client._backoff_delay(n, base=0.01, cap=0.05) for n in range(5)]
    assert seq == [0.01, 0.02, 0.04, 0.05, 0.05]


# --- D4: reconnect success restores healthy; failure threshold -> unavailable ---


@pytest.mark.asyncio
async def test_reconnect_success_restores_healthy_and_resets_attempts(monkeypatch):
    """A successful reconnect returns the server to healthy and zeroes the attempt count."""
    server = McpServerConfig(id="rc", url="http://rc.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "rc", server)
    mcp_client.set_health(server, mcp_client.HealthState.degraded)
    server._reconnect_attempts = 3

    async def fake_register(s):
        return None

    monkeypatch.setattr(mcp_client, "_register_server", fake_register)

    await mcp_client._attempt_reconnect(server)

    assert mcp_client.get_health(server) is mcp_client.HealthState.healthy
    assert server._reconnect_attempts == 0


@pytest.mark.asyncio
async def test_reconnect_failure_increments_attempts_stays_degraded(monkeypatch):
    server = McpServerConfig(id="rf", url="http://rf.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "rf", server)
    mcp_client.set_health(server, mcp_client.HealthState.degraded)

    async def fake_register(s):
        raise httpx.ConnectError("still down")

    monkeypatch.setattr(mcp_client, "_register_server", fake_register)
    monkeypatch.setattr(mcp_client, "_RECONNECT_MAX_ATTEMPTS", 5)

    await mcp_client._attempt_reconnect(server)

    assert server._reconnect_attempts == 1
    assert mcp_client.get_health(server) is mcp_client.HealthState.degraded


@pytest.mark.asyncio
async def test_reconnect_failure_reaching_threshold_marks_unavailable(monkeypatch):
    server = McpServerConfig(id="ru", url="http://ru.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "ru", server)
    mcp_client.set_health(server, mcp_client.HealthState.degraded)
    server._reconnect_attempts = 2  # one more failure hits threshold of 3

    async def fake_register(s):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(mcp_client, "_register_server", fake_register)
    monkeypatch.setattr(mcp_client, "_RECONNECT_MAX_ATTEMPTS", 3)

    await mcp_client._attempt_reconnect(server)

    assert mcp_client.get_health(server) is mcp_client.HealthState.unavailable


@pytest.mark.asyncio
async def test_manual_reconnect_recovers_unavailable_server(monkeypatch):
    """Manual reconnect entry re-tries an unavailable server and can restore it."""
    server = McpServerConfig(id="man", url="http://man.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "man", server)
    mcp_client.set_health(server, mcp_client.HealthState.unavailable)
    server._reconnect_attempts = 9

    async def fake_register(s):
        return None

    monkeypatch.setattr(mcp_client, "_register_server", fake_register)

    await mcp_client.reconnect("man")

    assert mcp_client.get_health(server) is mcp_client.HealthState.healthy
    assert server._reconnect_attempts == 0


# --- D3: periodic probe detects disconnect and triggers reconnect ---


@pytest.mark.asyncio
async def test_probe_http_unreachable_marks_degraded_and_triggers_reconnect(monkeypatch):
    """Probe failure (HTTP unreachable) -> degraded + reconnect scheduled."""
    import respx

    server = McpServerConfig(id="pb", url="http://pb.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "pb", server)

    scheduled: list = []
    monkeypatch.setattr(mcp_client, "_schedule_reconnect", lambda s: scheduled.append(s.id))

    with respx.mock:
        respx.post("http://pb.test/").mock(side_effect=httpx.ConnectError("down"))
        await mcp_client._probe_once(server)

    assert mcp_client.get_health(server) is mcp_client.HealthState.degraded
    assert scheduled == ["pb"]


@pytest.mark.asyncio
async def test_probe_http_healthy_stays_healthy(monkeypatch):
    import respx

    server = McpServerConfig(id="pok", url="http://pok.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "pok", server)
    monkeypatch.setattr(mcp_client, "_schedule_reconnect", lambda s: None)

    with respx.mock:
        respx.post("http://pok.test/").mock(
            side_effect=_make_streamable_handler(tool_result_text="ok")
        )
        await mcp_client._probe_once(server)

    assert mcp_client.get_health(server) is mcp_client.HealthState.healthy


@pytest.mark.asyncio
async def test_probe_stdio_dead_session_marks_degraded(monkeypatch):
    """A missing stdio session means the subprocess is gone -> degraded."""
    server = McpServerConfig(id="ps", transport="stdio", command="x")
    monkeypatch.setitem(mcp_client._server_registry, "ps", server)
    monkeypatch.setattr(mcp_client, "_schedule_reconnect", lambda s: None)
    mcp_client._active_sessions.pop("ps", None)

    await mcp_client._probe_once(server)

    assert mcp_client.get_health(server) is mcp_client.HealthState.degraded


@pytest.mark.asyncio
async def test_probe_skips_unavailable_server(monkeypatch):
    """An unavailable server is not auto-probed/reconnected (needs manual reconnect)."""
    import respx

    server = McpServerConfig(id="pu", url="http://pu.test", auth_type="none")
    monkeypatch.setitem(mcp_client._server_registry, "pu", server)
    mcp_client.set_health(server, mcp_client.HealthState.unavailable)

    scheduled: list = []
    monkeypatch.setattr(mcp_client, "_schedule_reconnect", lambda s: scheduled.append(s.id))

    route = respx.post("http://pu.test/")
    with respx.mock:
        respx.post("http://pu.test/").mock(return_value=httpx.Response(200))
        await mcp_client._probe_once(server)

    assert not route.called
    assert scheduled == []
    assert mcp_client.get_health(server) is mcp_client.HealthState.unavailable


# --- D6: background prober task lifecycle ---


@pytest.mark.asyncio
async def test_start_health_monitor_creates_task_and_stop_cancels_it():
    """start_health_monitor returns a running task; stop_health_monitor cancels it cleanly."""
    task = mcp_client.start_health_monitor(interval=0.01)
    assert task is not None
    assert not task.done()
    await mcp_client.stop_health_monitor()
    assert task.done()


@pytest.mark.asyncio
async def test_close_cancels_health_monitor(monkeypatch):
    """close() cancels the background health monitor, leaving no residual task."""
    monkeypatch.setattr(mcp_client, "_server_registry", {})
    monkeypatch.setattr(mcp_client, "_exit_stack", None)
    task = mcp_client.start_health_monitor(interval=0.01)
    await mcp_client.close()
    assert task.done()
    assert mcp_client._health_monitor_task is None
