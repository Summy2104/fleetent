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


# ── workspace path translation for stdio MCP args (host-process path view) ──


def test_host_workspace_dir_from_scope_key():
    from fleetent import paths
    from fleetent.integrations.sandbox import manager

    key = "slack:thread:C1:123.456"
    assert manager.host_workspace_dir(key) == paths.workspaces_dir() / manager._name_key(key)


def test_translate_workspace_arg_rewrites_workspace_prefix(tmp_path):
    host = tmp_path / "ws"
    assert mcp_client._translate_workspace_arg("/workspace/generated/x.png", host) == str(
        host / "generated" / "x.png"
    )
    assert mcp_client._translate_workspace_arg("/workspace", host) == str(host)


def test_translate_workspace_arg_leaves_non_workspace(tmp_path):
    host = tmp_path / "ws"
    for v in ["/etc/hosts", "hello", "generated/x.png", "/workspaceX/y"]:
        assert mcp_client._translate_workspace_arg(v, host) == v


def test_translate_workspace_args_recurses_dict_list(tmp_path):
    host = tmp_path / "ws"
    args = {"files": ["/workspace/a.png", "/etc/x"], "name": "x", "n": 3, "z": None}
    out = mcp_client._translate_workspace_args(args, host)
    assert out["files"][0] == str(host / "a.png")
    assert out["files"][1] == "/etc/x"
    assert out["name"] == "x" and out["n"] == 3 and out["z"] is None


def test_translate_relative_workspace_file(tmp_path):
    """A workspace-relative ref (image-gen "generated/<uuid>.png" the model passes verbatim)
    resolving to a real file under the workspace is translated to the host path."""
    host = tmp_path / "ws"
    (host / "generated").mkdir(parents=True)
    (host / "generated" / "x.png").write_bytes(b"png")
    assert mcp_client._translate_workspace_arg("generated/x.png", host) == str(
        host / "generated" / "x.png"
    )


def test_translate_relative_nonexistent_unchanged(tmp_path):
    host = tmp_path / "ws"
    host.mkdir()
    assert mcp_client._translate_workspace_arg("nope.png", host) == "nope.png"


def test_translate_relative_plaintext_unchanged(tmp_path):
    host = tmp_path / "ws"
    host.mkdir()
    for v in ["可爱小狗", "Hi,\n\n请欣赏这只小狗\n\nBest", "send_email"]:
        assert mcp_client._translate_workspace_arg(v, host) == v


def test_translate_relative_escape_blocked(tmp_path):
    host = tmp_path / "ws"
    host.mkdir()
    (tmp_path / "outside.png").write_bytes(b"x")  # real file OUTSIDE the workspace
    assert mcp_client._translate_workspace_arg("../outside.png", host) == "../outside.png"


def test_translate_args_relative_in_list(tmp_path):
    host = tmp_path / "ws"
    (host / "generated").mkdir(parents=True)
    (host / "generated" / "x.png").write_bytes(b"png")
    args = {"attachments": ["generated/x.png"], "subject": "可爱小狗"}
    out = mcp_client._translate_workspace_args(args, host)
    assert out["attachments"][0] == str(host / "generated" / "x.png")
    assert out["subject"] == "可爱小狗"
