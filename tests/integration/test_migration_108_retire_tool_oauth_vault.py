"""Integration tests for retiring the tool OAuth vault tables."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fleetent import agent_store
from tests.integration._migration_template import apply_migrations


def test_head_schema_drops_tool_oauth_vault_tables_and_delete_agent_still_works(
    tmp_path: Path, monkeypatch
) -> None:
    db = tmp_path / "mgmt.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent_store.create_agent("ops", "Ops.", ["shell"])
    assert agent_store.delete_agent("ops") is True

    conn = sqlite3.connect(db)
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    finally:
        conn.close()

    assert "external_services" not in tables
    assert "external_credentials" not in tables
    assert "agent_service_grants" not in tables
