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
