"""Unit tests for MCP resources/prompts synthetic tools (mcp-resources-prompts).

Mocked transports (monkeypatch _post_jsonrpc / fake stdio session); no real I/O.
"""

import json
import types

import pytest

import fleetent.integrations.mcp.client as mc


def _obj(**kw: object) -> types.SimpleNamespace:
    return types.SimpleNamespace(**kw)


class _Dumpable:
    """Mimics a pydantic result object exposing model_dump."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def model_dump(self, mode: str | None = None, exclude_none: bool = False) -> dict:
        return self._data


@pytest.fixture
def _clean_registry():
    import fleetent.tools.registry as tr

    reg = dict(tr._registry)
    srv = dict(mc._server_registry)
    sess = dict(mc._active_sessions)
    yield
    tr._registry.clear()
    tr._registry.update(reg)
    mc._server_registry.clear()
    mc._server_registry.update(srv)
    mc._active_sessions.clear()
    mc._active_sessions.update(sess)


# ── _utility_params ──────────────────────────────────────────────────────────


def test_utility_params_read_resource():
    assert mc._utility_params("read_resource", {"uri": "file:///a"}) == {"uri": "file:///a"}


def test_utility_params_get_prompt():
    assert mc._utility_params("get_prompt", {"name": "greet", "arguments": {"x": "1"}}) == {
        "name": "greet",
        "arguments": {"x": "1"},
    }


def test_utility_params_get_prompt_default_args():
    assert mc._utility_params("get_prompt", {"name": "greet"}) == {"name": "greet", "arguments": {}}


def test_utility_params_list_is_empty():
    assert mc._utility_params("list_resources", {}) == {}


# ── _jsonify ─────────────────────────────────────────────────────────────────


def test_jsonify_dict():
    assert json.loads(mc._jsonify({"a": 1})) == {"a": 1}


def test_jsonify_pydantic_like():
    out = mc._jsonify(_Dumpable({"resources": [{"uri": "x"}]}))
    assert json.loads(out) == {"resources": [{"uri": "x"}]}


# ── _call_utility over http ──────────────────────────────────────────────────


async def test_call_utility_http_list(monkeypatch, _clean_registry):
    server = mc.McpServerConfig(id="s", url="http://x", capabilities={"resources": {}})
    monkeypatch.setitem(mc._server_registry, (None, "s"), server)

    async def fake_post(client, srv, method, params, **kw):
        assert method == "resources/list"
        return {"result": {"resources": [{"uri": "u1"}]}}

    monkeypatch.setattr(mc, "_post_jsonrpc", fake_post)
    out = await mc._call_utility("s", "list_resources", {}, None)
    assert json.loads(out) == {"resources": [{"uri": "u1"}]}


async def test_call_utility_http_read_resource_forwards_uri(monkeypatch, _clean_registry):
    server = mc.McpServerConfig(id="s", url="http://x", capabilities={"resources": {}})
    monkeypatch.setitem(mc._server_registry, (None, "s"), server)
    seen: dict = {}

    async def fake_post(client, srv, method, params, **kw):
        seen["method"] = method
        seen["params"] = params
        return {"result": {"contents": []}}

    monkeypatch.setattr(mc, "_post_jsonrpc", fake_post)
    await mc._call_utility("s", "read_resource", {"uri": "file:///a"}, None)
    assert seen["method"] == "resources/read"
    assert seen["params"] == {"uri": "file:///a"}


# ── _call_utility over stdio ─────────────────────────────────────────────────


async def test_call_utility_stdio(monkeypatch, _clean_registry):
    server = mc.McpServerConfig(id="s", transport="stdio", capabilities={"resources": {}})
    monkeypatch.setitem(mc._server_registry, (None, "s"), server)

    class _Sess:
        async def list_resources(self):
            return _Dumpable({"resources": [{"uri": "r1"}]})

        async def read_resource(self, uri):
            return _Dumpable({"contents": [{"uri": str(uri)}]})

    monkeypatch.setitem(mc._active_sessions, (None, "s"), _Sess())
    assert json.loads(await mc._call_utility("s", "list_resources", {}, None)) == {
        "resources": [{"uri": "r1"}]
    }
    assert json.loads(await mc._call_utility("s", "read_resource", {"uri": "file:///a"}, None)) == {
        "contents": [{"uri": "file:///a"}]
    }


async def test_call_utility_unavailable_short_circuits(monkeypatch, _clean_registry):
    server = mc.McpServerConfig(id="s", url="http://x", capabilities={"resources": {}})
    server._health = mc.HealthState.unavailable
    monkeypatch.setitem(mc._server_registry, (None, "s"), server)
    out = await mc._call_utility("s", "list_resources", {}, None)
    assert "unavailable" in out.lower()


# ── _register_utility_tools: capability gating ───────────────────────────────


def test_register_utility_resources_only(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="s", capabilities={"resources": {}})
    mc._register_utility_tools(server, None)
    assert "s__list_resources" in tr._registry
    assert "s__read_resource" in tr._registry
    assert "s__list_prompts" not in tr._registry
    assert "s__get_prompt" not in tr._registry


def test_register_utility_prompts_only(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="s", capabilities={"prompts": {}})
    mc._register_utility_tools(server, None)
    assert "s__list_prompts" in tr._registry
    assert "s__get_prompt" in tr._registry
    assert "s__list_resources" not in tr._registry


def test_register_utility_both(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="s", capabilities={"resources": {}, "prompts": {}})
    mc._register_utility_tools(server, None)
    for name in ("s__list_resources", "s__read_resource", "s__list_prompts", "s__get_prompt"):
        assert name in tr._registry


def test_register_utility_none_when_no_caps(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="s", capabilities={})
    mc._register_utility_tools(server, None)
    assert not any(k.startswith("s__") for k in tr._registry)


def test_register_utility_scope_not_none_noop(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="s", capabilities={"resources": {}})
    mc._register_utility_tools(server, 5)
    assert "s__list_resources" not in tr._registry


def test_refresh_preserves_utility_tools(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="s", transport="stdio", capabilities={"resources": {}})
    tool = _obj(name="t1", description="d", inputSchema={"type": "object", "properties": {}})
    mc._reregister_stdio_tools(server, [tool], None)
    assert "s__t1" in tr._registry  # regular tool re-registered
    assert "s__list_resources" in tr._registry  # utility tool preserved across refresh
