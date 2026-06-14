"""Integration tests for the encrypted external credential store."""

from __future__ import annotations

import base64
import importlib
import importlib.util
import sqlite3

import pytest

from tests.integration._migration_template import apply_migrations


def _credential_store_module():
    spec = importlib.util.find_spec(
        "fleetent.platform.connector_management.external_credential_store"
    )
    assert spec is not None, "external_credential_store module is missing"
    return importlib.import_module("fleetent.platform.connector_management.external_credential_store")


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"0" * 32).decode("ascii"),
    )
    return db_path


def test_put_get_encrypts_and_isolates_by_user(store_db):
    store = _credential_store_module()
    store.put_oauth_credential(
        "u1",
        "github",
        {
            "access_token": "token-u1",
            "refresh_token": "refresh-u1",
            "scopes": ["repo"],
        },
        updated_by="u1",
    )

    credential = store.get_credential("u1", "github")

    assert credential is not None
    assert credential["status"] == "authorized"
    assert credential["payload"]["access_token"] == "token-u1"
    assert credential["payload"]["refresh_token"] == "refresh-u1"
    assert store.get_credential("u2", "github") is None

    conn = sqlite3.connect(store_db)
    try:
        row = conn.execute(
            """
            SELECT payload_ciphertext, status
            FROM external_credentials
            WHERE user_id = 'u1' AND service_id = 'github'
            """
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[1] == "authorized"
    assert row[0] != "token-u1"
    assert "token-u1" not in row[0]
    assert "refresh-u1" not in row[0]


def test_missing_secret_key_fails_without_writing_plaintext(store_db, monkeypatch):
    store = _credential_store_module()
    monkeypatch.delenv("FLEETENT_SECRET_KEY", raising=False)

    with pytest.raises(Exception, match="FLEETENT_SECRET_KEY"):
        store.put_oauth_credential(
            "u1",
            "github",
            {"access_token": "token-u1"},
            updated_by="u1",
        )

    conn = sqlite3.connect(store_db)
    try:
        rows = conn.execute("SELECT payload_ciphertext FROM external_credentials").fetchall()
    finally:
        conn.close()

    assert rows == []
