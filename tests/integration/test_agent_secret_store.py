"""Encrypted per-agent secret store (inject-mode credential values)."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import fleetent.user_store as us
from fleetent.config import Settings
from fleetent.db import create_database
from fleetent.platform.secret_management import agent_secret_store


def _migrate(db_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    db_path = tmp_path / "users.db"
    monkeypatch.setattr(us, "DB_PATH", db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode())
    _migrate(db_path)
    return tmp_path


def test_set_stores_ciphertext_not_plaintext(db):
    agent_secret_store.set_secret(1, "SUPPORT_SLACK_BOT", "xoxb-super-secret", updated_by="u1")

    row = (
        create_database(Settings().database_url)
        .execute(
            "SELECT ciphertext FROM agent_secrets WHERE agent_id = :aid AND env_name = :env",
            {"aid": 1, "env": "SUPPORT_SLACK_BOT"},
        )
        .fetchone()
    )
    assert "xoxb-super-secret" not in row["ciphertext"]
    assert agent_secret_store.get_decrypted(1, "SUPPORT_SLACK_BOT") == "xoxb-super-secret"


def test_status_reflects_presence(db):
    assert agent_secret_store.status(1, "TOK") == "unset"
    agent_secret_store.set_secret(1, "TOK", "v")
    assert agent_secret_store.status(1, "TOK") == "set"


def test_delete_clears(db):
    agent_secret_store.set_secret(1, "TOK", "v")
    agent_secret_store.delete_secret(1, "TOK")
    assert agent_secret_store.status(1, "TOK") == "unset"
    assert agent_secret_store.get_decrypted(1, "TOK") is None


def test_empty_value_rejected(db):
    with pytest.raises(ValueError):
        agent_secret_store.set_secret(1, "TOK", "")


def test_missing_secret_key_fails_loud(db, monkeypatch):
    monkeypatch.delenv("FLEETENT_SECRET_KEY", raising=False)
    with pytest.raises(agent_secret_store.SecretKeyError):
        agent_secret_store.set_secret(1, "TOK", "v")


def test_invalid_secret_key_fails_loud(db, monkeypatch):
    monkeypatch.setenv("FLEETENT_SECRET_KEY", "not-a-valid-fernet-key")
    with pytest.raises(agent_secret_store.SecretKeyError):
        agent_secret_store.set_secret(1, "TOK", "v")


def test_shared_scope_stores_with_null_agent(db):
    # agent_id=None is the shared (cross-agent) scope: one provider key, many agents.
    agent_secret_store.set_secret(None, "FLEETENT_MODEL_FAST_API_KEY", "sk-shared")
    assert agent_secret_store.status(None, "FLEETENT_MODEL_FAST_API_KEY") == "set"
    assert agent_secret_store.get_decrypted(None, "FLEETENT_MODEL_FAST_API_KEY") == "sk-shared"


def test_shared_and_per_agent_same_name_coexist(db):
    agent_secret_store.set_secret(None, "TOK", "shared-val")
    agent_secret_store.set_secret(1, "TOK", "agent-val")
    assert agent_secret_store.get_decrypted(None, "TOK") == "shared-val"
    assert agent_secret_store.get_decrypted(1, "TOK") == "agent-val"


def test_resolve_prefers_agent_then_falls_back_to_shared(db):
    agent_secret_store.set_secret(None, "TOK", "shared-val")
    # no per-agent slot yet -> resolves to shared
    assert agent_secret_store.get_resolved(1, "TOK") == "shared-val"
    # per-agent slot wins once present
    agent_secret_store.set_secret(1, "TOK", "agent-val")
    assert agent_secret_store.get_resolved(1, "TOK") == "agent-val"


def test_resolve_returns_none_when_neither_scope_set(db):
    assert agent_secret_store.get_resolved(1, "TOK") is None


def test_shared_delete_does_not_touch_agent_slot(db):
    agent_secret_store.set_secret(None, "TOK", "shared-val")
    agent_secret_store.set_secret(1, "TOK", "agent-val")
    agent_secret_store.delete_secret(None, "TOK")
    assert agent_secret_store.status(None, "TOK") == "unset"
    assert agent_secret_store.status(1, "TOK") == "set"
