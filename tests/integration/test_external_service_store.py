"""Integration tests for the external services registry store."""

from __future__ import annotations

import importlib
import importlib.util
import sqlite3

import pytest

from tests.integration._migration_template import apply_migrations


def _service_store_module():
    spec = importlib.util.find_spec("fleetent.platform.connector_management.external_service_store")
    assert spec is not None, "external_service_store module is missing"
    return importlib.import_module("fleetent.platform.connector_management.external_service_store")


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_migration_creates_external_services_table(store_db):
    conn = sqlite3.connect(store_db)
    try:
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert "external_services" in tables


def test_add_get_and_list_services(store_db):
    store = _service_store_module()
    store.add_service(
        "gdrive",
        "Google Drive",
        oauth_config={
            "authorize": "https://a",
            "token": "https://t",
            "scopes": ["drive.readonly"],
            "client_id": "cid",
            "client_secret": "shhh",
        },
    )

    service = store.get_service("gdrive")

    assert service["display_name"] == "Google Drive"
    assert service["protocol"] == "oauth2"
    assert service["oauth_config"]["client_id"] == "cid"
    assert "client_secret" not in service["oauth_config"]
    assert [item["service_id"] for item in store.list_services()] == ["gdrive"]


def test_duplicate_service_id_is_rejected(store_db):
    store = _service_store_module()
    store.add_service("github", "GitHub")

    with pytest.raises(sqlite3.IntegrityError):
        store.add_service("github", "GitHub duplicate")


def test_client_secret_never_hits_disk(store_db):
    store = _service_store_module()
    store.add_service(
        "gh",
        "GitHub",
        oauth_config={"client_id": "cid", "client_secret": "top-secret"},
    )

    conn = sqlite3.connect(store_db)
    try:
        raw = conn.execute(
            "SELECT oauth_config FROM external_services WHERE service_id = 'gh'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert "top-secret" not in (raw or "")
