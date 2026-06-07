"""Credential slot helpers: env-name derivation, collision check, mode-from-presence."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import fleetent.user_store as us
from fleetent.platform.secret_management import agent_secret_store, credential_service


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


def test_derive_env_name_upper_snake_with_namespace():
    assert (
        credential_service.derive_env_name("support-bot", "slack_bot")
        == "FLEETENT_AGENT_SUPPORT_BOT_SLACK_BOT"
    )


def test_derive_env_name_sanitizes_non_alnum():
    assert (
        credential_service.derive_env_name("acme.cs/team", "slack app")
        == "FLEETENT_AGENT_ACME_CS_TEAM_SLACK_APP"
    )


def test_derive_provider_env_name():
    assert (
        credential_service.derive_provider_env_name("fast-claude")
        == "FLEETENT_MODEL_FAST_CLAUDE_API_KEY"
    )


def test_derive_kb_env_name_strips_env_suffix():
    # field key carries the trailing _env; the derived var name drops it
    assert (
        credential_service.derive_kb_env_name("acme-drive", "access_token_env")
        == "FLEETENT_KB_ACME_DRIVE_ACCESS_TOKEN"
    )
    assert (
        credential_service.derive_kb_env_name("acme-conf", "api_token_env")
        == "FLEETENT_KB_ACME_CONF_API_TOKEN"
    )


def test_collision_check_raises_on_duplicate_env_names():
    with pytest.raises(ValueError):
        credential_service.assert_no_env_collisions(["A_TOK", "B_TOK", "A_TOK"])


def test_collision_check_passes_when_unique():
    credential_service.assert_no_env_collisions(["A_TOK", "B_TOK"])  # no raise


def test_slot_mode_operator_by_default(db):
    assert credential_service.slot_mode(1, "SOME_TOK") == "operator"


def test_slot_mode_inject_when_secret_set(db):
    agent_secret_store.set_secret(1, "SOME_TOK", "value")
    assert credential_service.slot_mode(1, "SOME_TOK") == "inject"
