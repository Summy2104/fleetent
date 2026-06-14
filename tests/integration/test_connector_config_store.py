"""Compatibility tests for the legacy connector_config_store import path."""

from __future__ import annotations

import sqlite3

import pytest

from fleetent.platform.connector_management import connector_config_store as store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_migration_creates_external_services_table(store_db):
    conn = sqlite3.connect(store_db)
    try:
        tables = {
            str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert "external_services" in tables
    assert "connectors" not in tables


def test_legacy_add_get_and_list_translate_shape(store_db):
    store.add_connector(
        "gdrive",
        "Google Drive",
        oauth_config={"client_id": "cid", "client_secret": "shhh"},
    )

    connector = store.get_connector("gdrive")

    assert connector is not None
    assert connector["id"] == "gdrive"
    assert connector["agent_id"] is None
    assert connector["oauth_config"]["client_id"] == "cid"
    assert "client_secret" not in connector["oauth_config"]
    assert [item["id"] for item in store.list_connectors()] == ["gdrive"]


def test_legacy_duplicate_global_rejected(store_db):
    store.add_connector("github", "GitHub")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_connector("github", "GitHub duplicate")


def test_legacy_agent_scoped_calls_are_rejected(store_db):
    with pytest.raises(ValueError, match="agent-scoped connectors were removed"):
        store.add_connector("github", "GitHub", agent_id=5)
