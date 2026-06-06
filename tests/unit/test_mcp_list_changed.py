"""Unit tests for stdio tools/list_changed dynamic refresh (mcp-dynamic-tools).

Mocked sessions/notifications; no real subprocess or stream.
"""

import asyncio
import types

import pytest

import fleetent.integrations.mcp.client as mc


def _obj(**kw: object) -> types.SimpleNamespace:
    return types.SimpleNamespace(**kw)


def _msg(method: str) -> types.SimpleNamespace:
    return _obj(root=_obj(method=method))


def _tool(name: str) -> types.SimpleNamespace:
    return _obj(
        name=name, description=f"{name} desc", inputSchema={"type": "object", "properties": {}}
    )


class _FakeStdioSession:
    def __init__(self, tools: list) -> None:
        self._tools = tools

    async def list_tools(self, cursor=None):
        return _obj(tools=self._tools, nextCursor=None)


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


# ── _is_tools_list_changed ───────────────────────────────────────────────────


def test_is_list_changed_true():
    assert mc._is_tools_list_changed(_msg("notifications/tools/list_changed")) is True


def test_is_list_changed_other_method_false():
    assert mc._is_tools_list_changed(_msg("notifications/progress")) is False


def test_is_list_changed_no_root_false():
    assert mc._is_tools_list_changed(_obj(foo="bar")) is False


# ── _reregister_stdio_tools ──────────────────────────────────────────────────


def test_reregister_adds_and_removes(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="srv", transport="stdio")
    mc._reregister_stdio_tools(server, [_tool("a"), _tool("b")], None)
    assert "srv__a" in tr._registry
    assert "srv__b" in tr._registry

    mc._reregister_stdio_tools(server, [_tool("a"), _tool("c")], None)
    assert "srv__a" in tr._registry
    assert "srv__c" in tr._registry
    assert "srv__b" not in tr._registry


def test_reregister_scope_not_none_noop(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="srv", transport="stdio")
    mc._reregister_stdio_tools(server, [_tool("a")], 5)
    assert "srv__a" not in tr._registry


# ── _refresh_stdio_tools (identity guard + re-register) ──────────────────────


async def _drain_tasks() -> None:
    for _ in range(6):
        await asyncio.sleep(0)


async def test_refresh_updates_registry(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="srv", transport="stdio")
    mc._reregister_stdio_tools(server, [_tool("a"), _tool("b")], None)
    session = _FakeStdioSession([_tool("a"), _tool("c")])
    mc._server_registry[(None, "srv")] = server
    mc._active_sessions[(None, "srv")] = session
    await mc._refresh_stdio_tools(server, None, session)
    assert "srv__c" in tr._registry
    assert "srv__b" not in tr._registry


async def test_refresh_identity_guard(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="srv", transport="stdio")
    mc._reregister_stdio_tools(server, [_tool("a")], None)
    stale = _FakeStdioSession([_tool("a"), _tool("c")])
    current = _FakeStdioSession([_tool("a")])
    mc._active_sessions[(None, "srv")] = current
    await mc._refresh_stdio_tools(server, None, stale)
    assert "srv__c" not in tr._registry  # stale-session notification ignored


# ── _make_message_handler (schedule refresh in a task) ───────────────────────


async def test_message_handler_schedules_refresh(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="srv", transport="stdio")
    mc._reregister_stdio_tools(server, [_tool("a")], None)
    session = _FakeStdioSession([_tool("a"), _tool("c")])
    mc._active_sessions[(None, "srv")] = session
    handler = mc._make_message_handler(server, None)
    await handler(_msg("notifications/tools/list_changed"))
    await _drain_tasks()
    assert "srv__c" in tr._registry


async def test_message_handler_ignores_non_list_changed(_clean_registry):
    import fleetent.tools.registry as tr

    server = mc.McpServerConfig(id="srv", transport="stdio")
    mc._reregister_stdio_tools(server, [_tool("a")], None)
    session = _FakeStdioSession([_tool("a"), _tool("c")])
    mc._active_sessions[(None, "srv")] = session
    handler = mc._make_message_handler(server, None)
    await handler(_msg("notifications/progress"))
    await _drain_tasks()
    assert "srv__c" not in tr._registry
