"""Unit tests for MCP client compliance (mcp-client-compliance).

Schema sanitization, protocol-version/capability capture, and tools/list cursor
pagination. No real I/O — mocked boundaries only (same style as test_mcp_degradation).
"""

import copy
import types

import pytest

import fleetent.integrations.mcp.client as mc


def _obj(**kw: object) -> types.SimpleNamespace:
    return types.SimpleNamespace(**kw)


# ── _sanitize_input_schema ───────────────────────────────────────────────────


def test_sanitize_missing_type_defaults_object():
    out = mc._sanitize_input_schema({"properties": {"x": {"type": "string"}}})
    assert out["type"] == "object"
    assert out["properties"] == {"x": {"type": "string"}}


def test_sanitize_missing_properties_added():
    out = mc._sanitize_input_schema({"type": "object"})
    assert out["properties"] == {}


def test_sanitize_non_dict_safe_default():
    assert mc._sanitize_input_schema(None) == {"type": "object", "properties": {}}
    assert mc._sanitize_input_schema("nope") == {"type": "object", "properties": {}}


def test_sanitize_definitions_renamed_to_defs_with_refs():
    schema = {
        "type": "object",
        "properties": {"f": {"$ref": "#/definitions/Foo"}},
        "definitions": {"Foo": {"type": "string"}},
    }
    out = mc._sanitize_input_schema(schema)
    assert "$defs" in out
    assert "definitions" not in out
    assert out["$defs"]["Foo"] == {"type": "string"}
    assert out["properties"]["f"]["$ref"] == "#/$defs/Foo"


def test_sanitize_nested_ref_rewritten():
    schema = {
        "type": "object",
        "properties": {"a": {"type": "array", "items": {"$ref": "#/definitions/Bar"}}},
        "definitions": {"Bar": {"type": "integer"}},
    }
    out = mc._sanitize_input_schema(schema)
    assert out["properties"]["a"]["items"]["$ref"] == "#/$defs/Bar"
    assert out["$defs"]["Bar"] == {"type": "integer"}


def test_sanitize_already_valid_preserved():
    schema = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "$defs": {"Y": {"type": "number"}},
    }
    out = mc._sanitize_input_schema(schema)
    assert out["type"] == "object"
    assert out["properties"] == {"x": {"type": "string"}}
    assert out["$defs"] == {"Y": {"type": "number"}}


def test_sanitize_does_not_mutate_input():
    schema = {"type": "object", "properties": {}, "definitions": {"A": {"type": "string"}}}
    original = copy.deepcopy(schema)
    mc._sanitize_input_schema(schema)
    assert schema == original


def test_sanitize_defs_present_no_clobber():
    schema = {
        "type": "object",
        "properties": {},
        "$defs": {"A": {"type": "string"}},
        "definitions": {"B": {"type": "number"}},
    }
    out = mc._sanitize_input_schema(schema)
    assert out["$defs"] == {"A": {"type": "string"}}  # existing $defs not clobbered


# ── protocol version + capability capture ────────────────────────────────────


class _FakeResp:
    def __init__(self, payload: dict, headers: dict | None = None) -> None:
        self._payload = payload
        self.headers = headers or {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload

    @property
    def text(self) -> str:
        import json as _json

        return _json.dumps(self._payload)


class _FakeClient:
    def __init__(self, payload: dict, resp_headers: dict | None = None) -> None:
        self._payload = payload
        self._resp_headers = resp_headers or {"content-type": "application/json"}
        self.posts: list[dict] = []

    async def post(
        self, url: str, json: dict | None = None, headers: dict | None = None
    ) -> _FakeResp:
        self.posts.append({"url": url, "json": json, "headers": headers})
        return _FakeResp(self._payload, self._resp_headers)


def test_config_has_version_and_caps_fields():
    s = mc.McpServerConfig(id="s")
    assert s.protocol_version is None
    assert s.capabilities == {}


async def test_open_session_captures_version_and_caps():
    server = mc.McpServerConfig(id="s", url="http://x")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}, "resources": {}}},
    }
    client = _FakeClient(payload, {"content-type": "application/json", "Mcp-Session-Id": "sess1"})
    await mc._open_session(client, server)
    assert server.protocol_version == "2025-03-26"
    assert server.capabilities == {"tools": {}, "resources": {}}
    assert server.session_id == "sess1"


async def test_open_session_defaults_version_when_omitted():
    server = mc.McpServerConfig(id="s", url="http://x")
    client = _FakeClient({"jsonrpc": "2.0", "id": 1, "result": {}})
    await mc._open_session(client, server)
    assert server.protocol_version == mc.PROTOCOL_VERSION
    assert server.capabilities == {}


def test_base_headers_includes_protocol_version_when_set():
    s = mc.McpServerConfig(id="s", url="http://x")
    s.protocol_version = "2025-06-18"
    headers = mc._base_headers(s)
    assert headers.get("MCP-Protocol-Version") == "2025-06-18"


def test_base_headers_omits_protocol_version_when_unset():
    s = mc.McpServerConfig(id="s", url="http://x")
    headers = mc._base_headers(s)
    assert "MCP-Protocol-Version" not in headers


# ── tools/list cursor pagination ─────────────────────────────────────────────


@pytest.fixture
def _clean_registry():
    import fleetent.tools.registry as tr

    reg_before = dict(tr._registry)
    srv_before = dict(mc._server_registry)
    sess_before = dict(mc._active_sessions)
    yield
    tr._registry.clear()
    tr._registry.update(reg_before)
    mc._server_registry.clear()
    mc._server_registry.update(srv_before)
    mc._active_sessions.clear()
    mc._active_sessions.update(sess_before)


async def test_list_all_tools_http_paginates(monkeypatch):
    server = mc.McpServerConfig(id="s", url="http://x")
    pages = {
        None: {"result": {"tools": [{"name": "a"}], "nextCursor": "c1"}},
        "c1": {"result": {"tools": [{"name": "b"}]}},
    }

    async def fake_post(client, srv, method, params, **kw):
        return pages[params.get("cursor")]

    monkeypatch.setattr(mc, "_post_jsonrpc", fake_post)
    tools = await mc._list_all_tools_http(None, server)
    assert [t["name"] for t in tools] == ["a", "b"]


async def test_list_all_tools_http_single_page(monkeypatch):
    server = mc.McpServerConfig(id="s", url="http://x")
    calls: list = []

    async def fake_post(client, srv, method, params, **kw):
        calls.append(params)
        return {"result": {"tools": [{"name": "only"}]}}

    monkeypatch.setattr(mc, "_post_jsonrpc", fake_post)
    tools = await mc._list_all_tools_http(None, server)
    assert [t["name"] for t in tools] == ["only"]
    assert len(calls) == 1


async def test_list_all_tools_http_bounded(monkeypatch):
    server = mc.McpServerConfig(id="s", url="http://x")
    calls: list = []

    async def fake_post(client, srv, method, params, **kw):
        calls.append(1)
        return {"result": {"tools": [{"name": "x"}], "nextCursor": "loop"}}

    monkeypatch.setattr(mc, "_post_jsonrpc", fake_post)
    tools = await mc._list_all_tools_http(None, server)
    assert len(calls) == mc._MAX_TOOL_PAGES  # bounded, not infinite
    assert len(tools) == mc._MAX_TOOL_PAGES


async def test_list_all_tools_stdio_paginates():
    class _Page:
        def __init__(self, tools, next_cursor=None):
            self.tools = tools
            self.nextCursor = next_cursor

    class _Sess:
        def __init__(self):
            self.cursors: list = []

        async def list_tools(self, cursor=None):
            self.cursors.append(cursor)
            if cursor is None:
                return _Page([_obj(name="a")], "c1")
            return _Page([_obj(name="b")], None)

    sess = _Sess()
    tools = await mc._list_all_tools_stdio(sess)
    assert [t.name for t in tools] == ["a", "b"]
    assert sess.cursors == [None, "c1"]


async def test_register_http_server_registers_all_pages(monkeypatch, _clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="ms", url="http://x")
    pages = {
        None: {
            "result": {
                "tools": [{"name": "t1", "inputSchema": {"type": "object", "properties": {}}}],
                "nextCursor": "c1",
            }
        },
        "c1": {
            "result": {
                "tools": [{"name": "t2", "inputSchema": {"type": "object", "properties": {}}}]
            }
        },
    }

    async def fake_open(client, srv):
        return None

    async def fake_post(client, srv, method, params, **kw):
        return pages[params.get("cursor")]

    monkeypatch.setattr(mc, "_open_session", fake_open)
    monkeypatch.setattr(mc, "_post_jsonrpc", fake_post)
    await mc._register_http_server(server)
    assert "ms__t1" in tr._registry
    assert "ms__t2" in tr._registry
