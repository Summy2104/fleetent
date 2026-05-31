import json

import httpx
import pytest

import fleetent.mcp_client as mcp_client
from fleetent.mcp_client import McpServerConfig, _make_tool_name


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
    from fleetent.mcp_client import McpServerConfig, _register_server

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

    from fleetent.mcp_client import McpServerConfig, _register_server

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

    import fleetent.mcp_client as mcp
    from fleetent.mcp_client import McpServerConfig

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
    import fleetent.mcp_client as mcp

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
