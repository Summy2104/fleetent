"""Unit: MCP stdio convention env injection for the /exchange partition tree.

Merge order is safe-whitelist < convention injection < explicit server env, so an
explicitly configured XDG is adopted in place; `file_isolation: off` skips the
convention entirely.
"""

from __future__ import annotations

from fleetent.integrations.mcp import client as mcp_client
from fleetent.integrations.mcp.client import McpServerConfig


def test_convention_injects_xdg_triple_pointing_at_partition_tree(tmp_path):
    server = McpServerConfig(id="gd", transport="stdio")
    env = mcp_client._subprocess_env(server, agent_home=tmp_path)
    base = tmp_path / "exchange" / "gd"
    assert env["XDG_DATA_HOME"] == str(base / "data")
    assert env["XDG_CONFIG_HOME"] == str(base / "config")
    assert env["XDG_CACHE_HOME"] == str(base / "cache")


def test_convention_cwd_points_at_partition_root(tmp_path):
    server = McpServerConfig(id="gd", transport="stdio")
    cwd = mcp_client._convention_cwd(server, tmp_path)
    assert cwd == tmp_path / "exchange" / "gd"


def test_explicit_env_overrides_convention(tmp_path):
    server = McpServerConfig(id="gw", transport="stdio", env={"XDG_DATA_HOME": "/custom/xdg/share"})
    env = mcp_client._subprocess_env(server, agent_home=tmp_path)
    assert env["XDG_DATA_HOME"] == "/custom/xdg/share"
    # the un-overridden convention members still injected
    assert env["XDG_CONFIG_HOME"] == str(tmp_path / "exchange" / "gw" / "config")


def test_file_isolation_off_skips_convention(tmp_path):
    server = McpServerConfig(id="gd", transport="stdio", file_isolation="off")
    env = mcp_client._subprocess_env(server, agent_home=tmp_path)
    assert "XDG_DATA_HOME" not in env


def test_no_agent_home_preserves_legacy_behavior():
    # Backward-compatible: without an agent_home no convention is injected.
    server = McpServerConfig(id="gd", transport="stdio", env={"FOO": "bar"})
    env = mcp_client._subprocess_env(server, agent_home=None)
    assert "XDG_DATA_HOME" not in env
    assert env["FOO"] == "bar"


# ── P1: stdio params cwd + server-root binding (wiring the dormant injection) ──


def test_stdio_params_sets_cwd_and_convention_env_when_agent_home_bound(tmp_path):
    server = McpServerConfig(id="gd", transport="stdio", command="x")
    server._agent_home = tmp_path
    params = mcp_client._stdio_params(server)
    assert params.cwd == str(tmp_path / "exchange" / "gd")
    assert params.env["XDG_DATA_HOME"] == str(tmp_path / "exchange" / "gd" / "data")
    assert (tmp_path / "exchange" / "gd").is_dir()  # cwd ensured to exist before spawn


def test_stdio_params_no_agent_home_legacy():
    server = McpServerConfig(id="gd", transport="stdio", command="x")
    params = mcp_client._stdio_params(server)
    assert params.cwd is None
    assert "XDG_DATA_HOME" not in params.env


def test_stdio_params_file_isolation_off_no_cwd(tmp_path):
    server = McpServerConfig(id="gd", transport="stdio", command="x", file_isolation="off")
    server._agent_home = tmp_path
    params = mcp_client._stdio_params(server)
    assert params.cwd is None
    assert "XDG_DATA_HOME" not in params.env


def test_bind_exchange_root_registers_convention_root(tmp_path, monkeypatch):
    from fleetent import artifact_exchange

    monkeypatch.setattr(artifact_exchange, "_server_roots", {})
    server = McpServerConfig(id="gd", transport="stdio", command="x")
    mcp_client._bind_exchange_root(server, tmp_path)
    assert artifact_exchange._server_roots["gd"] == tmp_path / "exchange" / "gd" / "data"


def test_bind_exchange_root_adopts_explicit_xdg(tmp_path, monkeypatch):
    from fleetent import artifact_exchange

    monkeypatch.setattr(artifact_exchange, "_server_roots", {})
    server = McpServerConfig(
        id="gw", transport="stdio", command="x", env={"XDG_DATA_HOME": str(tmp_path / "xdg")}
    )
    mcp_client._bind_exchange_root(server, tmp_path)
    assert artifact_exchange._server_roots["gw"] == tmp_path / "xdg"


def test_bind_exchange_root_skips_without_agent_home_or_isolation_off(monkeypatch):
    from fleetent import artifact_exchange

    monkeypatch.setattr(artifact_exchange, "_server_roots", {})
    s1 = McpServerConfig(id="gd", transport="stdio", command="x")
    mcp_client._bind_exchange_root(s1, None)
    s2 = McpServerConfig(id="gw", transport="stdio", command="x", file_isolation="off")
    mcp_client._bind_exchange_root(s2, "/home")
    assert artifact_exchange._server_roots == {}
