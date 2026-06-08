"""Integration tests for per-agent encrypted secret values."""

import base64
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import fleetent.agent_store as agent_store
from fleetent.platform.agent_lifecycle import secret_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"0" * 32).decode("ascii"),
    )
    return db_path


def _ciphertext(db_path: Path, agent_id: int, env_name: str) -> str | None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT ciphertext FROM agent_secrets WHERE agent_id = ? AND env_name = ?",
            (agent_id, env_name),
        ).fetchone()
    return None if row is None else str(row[0])


def test_set_encrypts_and_get_decrypted_round_trips(db):
    agent = agent_store.create_agent("support", "p", [])

    secret_store.set(agent.id, "FLEETENT_AGENT_SUPPORT_MODEL", "sk-live-secret", "admin")

    ciphertext = _ciphertext(db, agent.id, "FLEETENT_AGENT_SUPPORT_MODEL")
    assert ciphertext is not None
    assert ciphertext != "sk-live-secret"
    assert "sk-live-secret" not in ciphertext
    assert secret_store.get_decrypted(agent.id, "FLEETENT_AGENT_SUPPORT_MODEL") == "sk-live-secret"


def test_status_and_delete_never_return_plaintext(db):
    agent = agent_store.create_agent("support", "p", [])
    env_name = "FLEETENT_AGENT_SUPPORT_MODEL"

    assert secret_store.status(agent.id, env_name) == "unset"
    secret_store.set(agent.id, env_name, "sk-live-secret", "admin")
    assert secret_store.status(agent.id, env_name) == "set"
    secret_store.delete(agent.id, env_name)
    assert secret_store.status(agent.id, env_name) == "unset"
    assert secret_store.get_decrypted(agent.id, env_name) is None


def test_missing_or_invalid_secret_key_fails_loud(db, monkeypatch):
    agent = agent_store.create_agent("support", "p", [])

    monkeypatch.delenv("FLEETENT_SECRET_KEY", raising=False)
    with pytest.raises(secret_store.SecretKeyError, match="FLEETENT_SECRET_KEY"):
        secret_store.set(agent.id, "FLEETENT_AGENT_SUPPORT_MODEL", "sk-live-secret")

    monkeypatch.setenv("FLEETENT_SECRET_KEY", "not-a-fernet-key")
    with pytest.raises(secret_store.SecretKeyError, match="FLEETENT_SECRET_KEY"):
        secret_store.get_decrypted(agent.id, "FLEETENT_AGENT_SUPPORT_MODEL")


def test_empty_secret_value_is_rejected(db):
    agent = agent_store.create_agent("support", "p", [])

    with pytest.raises(ValueError, match="empty"):
        secret_store.set(agent.id, "FLEETENT_AGENT_SUPPORT_MODEL", "")


def test_shared_scope_stores_with_null_agent(db):
    # agent_id=None is the shared (cross-agent) scope used by provider/connector keys
    secret_store.set(None, "FLEETENT_KB_DRIVE_TOKEN", "ya29-shared")
    assert secret_store.status(None, "FLEETENT_KB_DRIVE_TOKEN") == "set"
    assert secret_store.get_decrypted(None, "FLEETENT_KB_DRIVE_TOKEN") == "ya29-shared"


def test_shared_and_per_agent_same_name_coexist(db):
    agent = agent_store.create_agent("support", "p", [])
    secret_store.set(None, "TOK", "shared-val")
    secret_store.set(agent.id, "TOK", "agent-val")
    assert secret_store.get_decrypted(None, "TOK") == "shared-val"
    assert secret_store.get_decrypted(agent.id, "TOK") == "agent-val"


def test_get_resolved_prefers_agent_then_shared(db):
    agent = agent_store.create_agent("support", "p", [])
    secret_store.set(None, "TOK", "shared-val")
    assert secret_store.get_resolved(agent.id, "TOK") == "shared-val"  # falls back to shared
    secret_store.set(agent.id, "TOK", "agent-val")
    assert secret_store.get_resolved(agent.id, "TOK") == "agent-val"  # per-agent wins
    assert secret_store.get_resolved(agent.id, "MISSING") is None
