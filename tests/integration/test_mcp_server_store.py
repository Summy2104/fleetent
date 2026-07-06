from __future__ import annotations

import sqlite3

import fleetent.platform.connector_management.mcp_server_store as store
from tests.integration._migration_template import apply_migrations


def test_store_uses_auth_config_without_api_key_env(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    store.add_mcp_server(
        None,
        "github",
        transport="http",
        url="https://mcp.internal/github",
        auth_type="api_key",
        auth_config={"key_env": "FLEETENT_GITHUB_MCP_KEY"},
        headers={"X-Trace": "1"},
    )
    store.edit_mcp_server(None, "github", auth_config={"key_env": "FLEETENT_GITHUB_MCP_KEY_V2"})

    row = store.get_mcp_server(None, "github")
    assert row is not None
    assert row["auth_type"] == "api_key"
    assert row["auth_config"] == {"key_env": "FLEETENT_GITHUB_MCP_KEY_V2"}
    assert "api_key_env" not in row

    listed = store.list_mcp_servers(None)
    assert listed == [row]

    with sqlite3.connect(db_path) as conn:
        cols = {info[1] for info in conn.execute("PRAGMA table_info(mcp_servers)")}
        auth_config = conn.execute(
            "SELECT auth_config FROM mcp_servers WHERE server_id = ?",
            ("github",),
        ).fetchone()[0]

    assert "auth_config" in cols
    assert "api_key_env" not in cols
    assert auth_config == '{"key_env": "FLEETENT_GITHUB_MCP_KEY_V2"}'


def test_xfleetent_fields_round_trip(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    store.add_mcp_server(
        None,
        "billing",
        transport="stdio",
        command="npx",
        degrade_mode="strict",
        file_root="/exchange/billing",
        file_isolation="off",
    )

    row = store.get_mcp_server(None, "billing")
    assert row is not None
    assert row["degrade_mode"] == "strict"
    assert row["file_root"] == "/exchange/billing"
    assert row["file_isolation"] == "off"
    # approval_rules is no longer a server-level field (moved to per-agent binding).
    assert "approval_rules" not in row

    # Editing a subset leaves the untouched columns intact.
    store.edit_mcp_server(None, "billing", degrade_mode="silent")
    edited = store.get_mcp_server(None, "billing")
    assert edited is not None
    assert edited["degrade_mode"] == "silent"
    assert edited["file_isolation"] == "off"

    # Omitted fields fall back to the McpServerSettings defaults.
    store.add_mcp_server(None, "plain", transport="stdio", command="echo")
    plain = store.get_mcp_server(None, "plain")
    assert plain is not None
    assert plain["degrade_mode"] == "degrade"
    assert plain["file_root"] == ""
    assert plain["file_isolation"] == "on"

    # Migration 118 added the three server-level x-fleetent columns; 119 dropped approval_rules.
    with sqlite3.connect(db_path) as conn:
        cols = {info[1] for info in conn.execute("PRAGMA table_info(mcp_servers)")}
    assert {"degrade_mode", "file_root", "file_isolation"} <= cols
    assert "approval_rules" not in cols
