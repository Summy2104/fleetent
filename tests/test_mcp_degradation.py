"""Tests for MCP graceful degradation (MCP4): availability, schema filtering, modes."""

import fleetent.mcp_client as mc
import fleetent.tool_registry as tr
from fleetent.mcp_client import HealthState, McpServerConfig

# ── is_server_available (D1) ─────────────────────────────────────────────────


def test_available_when_healthy_no_auth():
    assert mc.is_server_available(McpServerConfig(id="s")) is True


def test_unavailable_when_degraded():
    s = McpServerConfig(id="s")
    s._health = HealthState.degraded
    assert mc.is_server_available(s) is False


def test_unavailable_when_connection_unavailable():
    s = McpServerConfig(id="s")
    s._health = HealthState.unavailable
    assert mc.is_server_available(s) is False


def test_unavailable_when_oauth_auth_unavailable():
    s = McpServerConfig(id="s", auth_type="oauth2")
    s._auth_unavailable = True
    assert mc.is_server_available(s) is False


def test_oauth_available_when_auth_ok_and_healthy():
    s = McpServerConfig(id="s", auth_type="oauth2")
    assert mc.is_server_available(s) is True


def test_api_key_healthy_available():
    assert mc.is_server_available(McpServerConfig(id="s", auth_type="api_key")) is True


# ── degrade_mode field (D3) ──────────────────────────────────────────────────


def test_degrade_mode_default():
    assert McpServerConfig(id="s").degrade_mode == "degrade"


def test_degrade_mode_accepts_valid():
    assert McpServerConfig(id="s", degrade_mode="strict").degrade_mode == "strict"
    assert McpServerConfig(id="s", degrade_mode="silent").degrade_mode == "silent"


def test_degrade_mode_invalid_falls_back_to_degrade():
    assert McpServerConfig(id="s", degrade_mode="bogus").degrade_mode == "degrade"


# ── tool_registry schema visibility hook (D4) ────────────────────────────────


def test_get_schemas_no_filter_returns_all(monkeypatch):
    monkeypatch.setattr(tr, "_schema_visibility_filter", None)

    @tr.tool
    def _vis_a() -> str:
        return "x"

    names = {s["function"]["name"] for s in tr.get_schemas()}
    assert "_vis_a" in names


def test_get_schemas_filter_drops_invisible(monkeypatch):
    @tr.tool
    def _vis_keep() -> str:
        return "x"

    @tr.tool
    def _vis_drop() -> str:
        return "x"

    monkeypatch.setattr(tr, "_schema_visibility_filter", lambda name: name != "_vis_drop")
    names = {s["function"]["name"] for s in tr.get_schemas()}
    assert "_vis_keep" in names
    assert "_vis_drop" not in names  # filtered view; registry entry NOT deleted
    assert "_vis_drop" in tr._registry  # still registered (recovery = predicate flips)


def test_set_schema_visibility_filter(monkeypatch):
    monkeypatch.setattr(tr, "_schema_visibility_filter", None)
    tr.set_schema_visibility_filter(lambda name: False)
    try:
        assert tr.get_schemas() == []  # everything filtered out
    finally:
        tr.set_schema_visibility_filter(None)
    assert tr._schema_visibility_filter is None


# ── mcp_client schema visibility predicate + recovery (D2/D4) ────────────────


def test_schema_visibility_drops_unavailable_mcp_tools(monkeypatch):
    healthy = McpServerConfig(id="srvok")
    bad = McpServerConfig(id="srvbad")
    bad._health = HealthState.unavailable
    monkeypatch.setitem(mc._server_registry, "srvok", healthy)
    monkeypatch.setitem(mc._server_registry, "srvbad", bad)
    assert mc._schema_visibility("srvok__tool") is True
    assert mc._schema_visibility("srvbad__tool") is False
    assert mc._schema_visibility("plain_builtin_tool") is True  # non-MCP kept
    assert mc._schema_visibility("unknown__tool") is True  # unknown server kept


def test_recovery_reexposes_tool(monkeypatch):
    s = McpServerConfig(id="recsrv")
    s._health = HealthState.degraded
    monkeypatch.setitem(mc._server_registry, "recsrv", s)
    assert mc._schema_visibility("recsrv__t") is False
    mc.reset_health(s)  # connection restored
    assert mc._schema_visibility("recsrv__t") is True  # no re-registration needed


# ── strict-mode query (D3/D5) ────────────────────────────────────────────────


def test_unavailable_strict_server_ids(monkeypatch):
    strict_bad = McpServerConfig(id="sb", degrade_mode="strict")
    strict_bad._health = HealthState.unavailable
    strict_ok = McpServerConfig(id="sok", degrade_mode="strict")
    degrade_bad = McpServerConfig(id="db", degrade_mode="degrade")
    degrade_bad._health = HealthState.unavailable
    monkeypatch.setattr(
        mc, "_server_registry", {"sb": strict_bad, "sok": strict_ok, "db": degrade_bad}
    )
    monkeypatch.setattr(mc, "_failed_strict_servers", set())
    ids = mc.unavailable_strict_server_ids()
    assert ids == {"sb"}  # strict+unavailable only; strict+ok and degrade+bad excluded


async def test_register_all_strict_startup_failure_tracked(monkeypatch):
    # register_all installs the global schema filter; monkeypatch it so it reverts.
    monkeypatch.setattr(tr, "_schema_visibility_filter", None)
    strict = McpServerConfig(id="failstrict", degrade_mode="strict")
    healthy = McpServerConfig(id="okserver")
    monkeypatch.setattr(mc, "_server_registry", {})
    monkeypatch.setattr(mc, "_failed_strict_servers", set())

    async def fake_register(server):
        if server.id == "failstrict":
            raise RuntimeError("connect failed")
        mc._server_registry[server.id] = server

    monkeypatch.setattr(mc, "_register_server", fake_register)
    await mc.register_all([strict, healthy])
    # Platform start not blocked; healthy server registered; strict failure tracked.
    assert "okserver" in mc._server_registry
    assert "failstrict" in mc.unavailable_strict_server_ids()


# ── MCP4 review: unavailable_servers + strict stop + degrade/silent logging ──


def test_unavailable_servers_lists_modes(monkeypatch):
    ok = McpServerConfig(id="ok")
    deg = McpServerConfig(id="deg", degrade_mode="degrade")
    deg._health = HealthState.unavailable
    sil = McpServerConfig(id="sil", degrade_mode="silent")
    sil._health = HealthState.unavailable
    st = McpServerConfig(id="st", degrade_mode="strict")
    st._health = HealthState.unavailable
    monkeypatch.setattr(mc, "_server_registry", {"ok": ok, "deg": deg, "sil": sil, "st": st})
    monkeypatch.setattr(mc, "_failed_strict_servers", {"failst"})
    got = dict(mc.unavailable_servers())
    assert got == {"deg": "degrade", "sil": "silent", "st": "strict", "failst": "strict"}


def test_agent_bound_to_server(monkeypatch):
    import fleetent.agent_loop as al

    monkeypatch.setattr(mc, "_server_registry", {})
    monkeypatch.setitem(tr._registry, "srv__tool", (lambda: "x", {}))
    assert al._agent_bound_to_server("srv", None) is True  # all tools → bound
    assert al._agent_bound_to_server("srv", ["srv__*"]) is True
    assert al._agent_bound_to_server("srv", ["other__*"]) is False


def test_degrade_silent_log_levels(monkeypatch):
    import fleetent.agent_loop as al

    deg = McpServerConfig(id="deg", degrade_mode="degrade")
    deg._health = HealthState.unavailable
    sil = McpServerConfig(id="sil", degrade_mode="silent")
    sil._health = HealthState.unavailable
    monkeypatch.setattr(mc, "_server_registry", {"deg": deg, "sil": sil})
    monkeypatch.setattr(mc, "_failed_strict_servers", set())

    from unittest.mock import MagicMock

    spy = MagicMock()
    monkeypatch.setattr(al, "logger", spy)
    blocked = al._strict_blocked_servers(None)  # None → bound to both
    assert blocked == []  # neither is strict
    assert spy.warning.called  # degrade → warning (prominent)
    assert spy.debug.called  # silent → debug (quiet) — the distinction
