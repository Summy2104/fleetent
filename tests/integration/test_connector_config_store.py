"""Tests for connector_config_store (migration 013, db runtime). Secret never stored."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent import connector_config_store as store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_migration_creates_table(store_db):
    conn = sqlite3.connect(store_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "connectors" in tables


def test_add_and_get(store_db):
    store.add_connector(
        "gdrive",
        "Google Drive",
        oauth_config={
            "authorize": "https://a",
            "token": "https://t",
            "scopes": ["drive.readonly"],
            "client_id": "cid",
        },
    )
    c = store.get_connector("gdrive")
    assert c["display_name"] == "Google Drive"
    assert c["oauth_config"]["client_id"] == "cid"
    assert c["protocol"] == "oauth2"


def test_client_secret_never_stored(store_db):
    store.add_connector(
        "gh",
        "GitHub",
        oauth_config={"client_id": "cid", "client_secret": "shhh"},
    )
    c = store.get_connector("gh")
    assert "client_secret" not in c["oauth_config"]
    # confirm it's not in the raw row either
    conn = sqlite3.connect(store_db)
    raw = conn.execute("SELECT oauth_config FROM connectors WHERE id='gh'").fetchone()[0]
    conn.close()
    assert "shhh" not in (raw or "")


def test_edit_strips_secret(store_db):
    store.add_connector("gh", "GitHub", oauth_config={"client_id": "cid"})
    store.edit_connector("gh", oauth_config={"client_id": "cid2", "client_secret": "leak"})
    c = store.get_connector("gh")
    assert c["oauth_config"]["client_id"] == "cid2"
    assert "client_secret" not in c["oauth_config"]


def test_list(store_db):
    store.add_connector("a", "A")
    store.add_connector("b", "B")
    assert {c["id"] for c in store.list_connectors()} == {"a", "b"}
