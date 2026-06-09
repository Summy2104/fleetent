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


def test_config_has_version_and_caps_fields():
    s = mc.McpServerConfig(id="s")
    assert s.protocol_version is None
    assert s.capabilities == {}


def test_init_result_captures_version_and_caps():
    # The SDK ClientSession.initialize() result is coerced + captured per-server.
    server = mc.McpServerConfig(id="s", url="http://x")
    init = _obj(protocolVersion="2025-03-26", capabilities={"tools": {}, "resources": {}})
    mc._capture_init_result(server, mc._init_result_to_dict(init))
    assert server.protocol_version == "2025-03-26"
    assert server.capabilities == {"tools": {}, "resources": {}}


def test_init_result_defaults_version_when_omitted():
    server = mc.McpServerConfig(id="s", url="http://x")
    init = _obj(protocolVersion=None, capabilities=None)
    mc._capture_init_result(server, mc._init_result_to_dict(init))
    assert server.protocol_version == mc.PROTOCOL_VERSION
    assert server.capabilities == {}


async def test_http_headers_omit_protocol_version_sdk_owned():
    # The protocol-version header is negotiated and emitted by the SDK ClientSession; the
    # client's own header builder must NOT set MCP-Protocol-Version (no hand-rolled value).
    s = mc.McpServerConfig(id="s", url="http://x")
    s.protocol_version = "2025-06-18"
    headers = await mc._http_headers(s)
    assert "MCP-Protocol-Version" not in headers


# ── tools/list cursor pagination (one SDK-session path for all transports) ────


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


class _Page:
    def __init__(self, tools, next_cursor=None):
        self.tools = tools
        self.nextCursor = next_cursor


async def test_list_all_tools_paginates():
    class _Sess:
        def __init__(self):
            self.cursors: list = []

        async def list_tools(self, cursor=None):
            self.cursors.append(cursor)
            if cursor is None:
                return _Page([_obj(name="a")], "c1")
            return _Page([_obj(name="b")], None)

    sess = _Sess()
    tools = await mc._list_all_tools(sess)
    assert [t.name for t in tools] == ["a", "b"]
    assert sess.cursors == [None, "c1"]


async def test_list_all_tools_single_page():
    class _Sess:
        def __init__(self):
            self.calls = 0

        async def list_tools(self, cursor=None):
            self.calls += 1
            return _Page([_obj(name="only")], None)

    sess = _Sess()
    tools = await mc._list_all_tools(sess)
    assert [t.name for t in tools] == ["only"]
    assert sess.calls == 1


async def test_list_all_tools_bounded():
    class _Sess:
        def __init__(self):
            self.calls = 0

        async def list_tools(self, cursor=None):
            self.calls += 1
            return _Page([_obj(name="x")], "loop")  # always advertises a next cursor

    sess = _Sess()
    tools = await mc._list_all_tools(sess)
    assert sess.calls == mc._MAX_TOOL_PAGES  # bounded, not infinite
    assert len(tools) == mc._MAX_TOOL_PAGES


async def test_register_session_server_registers_all_pages(monkeypatch, _clean_registry):
    import contextlib

    import fleetent.tools.registry as tr

    page_tools = {
        None: _Page(
            [_obj(name="t1", description="d", inputSchema={"type": "object", "properties": {}})],
            "c1",
        ),
        "c1": _Page(
            [_obj(name="t2", description="d", inputSchema={"type": "object", "properties": {}})],
            None,
        ),
    }

    class _Sess:
        async def initialize(self):
            return _obj(protocolVersion="2025-11-25", capabilities={})

        async def list_tools(self, cursor=None):
            return page_tools[cursor]

    @contextlib.asynccontextmanager
    async def _fake_transport(*a, **k):
        yield ("read", "write", None)

    @contextlib.asynccontextmanager
    async def _session_cm(*a, **k):
        yield _Sess()

    monkeypatch.setattr(mc, "streamablehttp_client", lambda *a, **k: _fake_transport())
    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _session_cm())

    server = mc.McpServerConfig(id="ms", url="http://x")
    await mc._register_session_server(server)
    assert "ms__t1" in tr._registry
    assert "ms__t2" in tr._registry
