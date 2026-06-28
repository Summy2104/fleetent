"""Integration tests for the external credential vault migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from fleetent import agent_store


def _upgrade_to(db_path: Path, revision: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, revision)


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def _index_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
    return {str(row[1]) for row in rows}


def _pk_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    ordered = sorted((int(row[5]), str(row[1])) for row in rows if int(row[5]) > 0)
    return [name for _, name in ordered]


def _foreign_keys(conn: sqlite3.Connection, table: str) -> list[tuple[object, ...]]:
    return conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()


def test_migration_093_replaces_connectors_with_external_services(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "093")

    conn = sqlite3.connect(db)
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        columns = _table_columns(conn, "external_services")
        indexes = _index_names(conn, "external_services")
    finally:
        conn.close()

    assert "external_services" in tables
    assert "connectors" not in tables
    assert "agent_id" not in columns
    assert "ux_connectors_agent_scope" not in indexes
    assert "ux_connectors_global_scope" not in indexes


def test_migration_093_renames_agent_oauth_bindings_to_agent_service_grants(
    tmp_path: Path,
) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "093")

    conn = sqlite3.connect(db)
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        columns = _table_columns(conn, "agent_service_grants")
        pk_columns = _pk_columns(conn, "agent_service_grants")
        fk_rows = _foreign_keys(conn, "agent_service_grants")
        default_row = conn.execute(
            "INSERT INTO agent_service_grants (agent_id, service_id, created_at, created_by) "
            "VALUES (1, 'github', '2026-06-14T00:00:00+00:00', 'seed') "
            "RETURNING run_as"
        ).fetchone()
        conn.rollback()
    finally:
        conn.close()

    assert "agent_service_grants" in tables
    assert "agent_oauth_bindings" not in tables
    assert columns == ["agent_id", "service_id", "run_as", "created_at", "created_by"]
    assert pk_columns == ["agent_id", "service_id"]
    assert default_row is not None and default_row[0] == "user"
    assert any(
        row[2] == "agents" and row[3] == "agent_id" and row[4] == "id" and row[6] == "CASCADE"
        for row in fk_rows
    )


def test_migration_093_adds_external_credentials(tmp_path: Path) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "093")

    conn = sqlite3.connect(db)
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        columns = _table_columns(conn, "external_credentials")
        pk_columns = _pk_columns(conn, "external_credentials")
    finally:
        conn.close()

    assert "external_credentials" in tables
    assert columns == [
        "user_id",
        "service_id",
        "payload_ciphertext",
        "status",
        "updated_at",
        "updated_by",
    ]
    assert pk_columns == ["user_id", "service_id"]


def test_upgrade_to_093_preserves_rows_and_delete_agent_cascades_service_grants(
    tmp_path: Path, monkeypatch
) -> None:
    db = tmp_path / "mgmt.db"
    _upgrade_to(db, "091")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")

    agent = agent_store.create_agent("ops", "Ops.", ["shell"])

    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO connectors
                (agent_id, id, display_name, protocol, oauth_config, enabled,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                "github",
                "GitHub",
                "oauth2",
                '{"client_id":"cid"}',
                1,
                "2026-06-14T00:00:00+00:00",
                "2026-06-14T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO agent_oauth_bindings (agent_id, connector_id, created_at, created_by)
            VALUES (?, ?, ?, ?)
            """,
            (agent.id, "github", "2026-06-14T00:00:00+00:00", "seed"),
        )
        conn.commit()
    finally:
        conn.close()

    _upgrade_to(db, "093")
    assert agent_store.delete_agent("ops") is True

    conn = sqlite3.connect(db)
    try:
        migrated_service = conn.execute(
            "SELECT service_id, display_name FROM external_services WHERE service_id = 'github'"
        ).fetchone()
        grant_count = conn.execute(
            "SELECT COUNT(*) FROM agent_service_grants WHERE agent_id = ?",
            (agent.id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert migrated_service == ("github", "GitHub")
    assert grant_count == 0
