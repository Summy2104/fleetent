"""Integration tests for per-agent credential slot metadata."""

import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import fleetent.agent_store as agent_store
from fleetent.platform.agent_lifecycle import credential_slots, materialize


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
    return db_path


def _model_overrides(agent_id: int) -> dict:
    db_runtime = agent_store._db()
    row = (
        db_runtime.execute(
            "SELECT av.model_overrides FROM agent_versions av "
            "JOIN agents a ON a.active_version_id = av.id WHERE a.id = :agent_id",
            {"agent_id": agent_id},
        )
        .fetchone()
    )
    assert row is not None
    return json.loads(row["model_overrides"])


def test_new_slot_defaults_operator_and_derives_env_name(db):
    agent = agent_store.create_agent("support-bot", "p", [])

    slot = credential_slots.ensure_slot(agent, "slack_bot")

    assert slot.mode == "operator"
    assert slot.env_name == "FLEETENT_AGENT_SUPPORT_BOT_SLACK_BOT"
    stored = _model_overrides(agent.id)[credential_slots.RESERVED_KEY]["slack_bot"]
    assert stored == {
        "env_name": "FLEETENT_AGENT_SUPPORT_BOT_SLACK_BOT",
        "mode": "operator",
    }


def test_slot_env_name_does_not_drift_on_agent_rename(db):
    agent = agent_store.create_agent("support-bot", "p", [])
    original = credential_slots.ensure_slot(agent, "slack_bot")

    agent_store.rename_agent("support-bot", "renamed-bot")
    renamed = agent_store.get_by_name("renamed-bot")
    assert renamed is not None
    after_rename = credential_slots.ensure_slot(renamed, "slack_bot")

    assert after_rename.env_name == original.env_name


def test_duplicate_env_name_is_rejected(db):
    agent = agent_store.create_agent("support-bot", "p", [])
    credential_slots.ensure_slot(agent, "slack_bot", env_name="FLEETENT_AGENT_SUPPORT_SHARED")

    with pytest.raises(ValueError, match="duplicate env_name"):
        credential_slots.ensure_slot(agent, "slack_app", env_name="FLEETENT_AGENT_SUPPORT_SHARED")


def test_slot_metadata_is_not_materialized_to_agent_yaml(db, tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    agent = agent_store.create_agent("support-bot", "p", [])
    credential_slots.ensure_slot(agent, "slack_bot", mode="inject")

    exported = materialize.agent_file_from_store(agent_store.get_by_name("support-bot"))
    home = materialize.write_home(exported)
    text = (home / "agent.yaml").read_text(encoding="utf-8")

    assert credential_slots.RESERVED_KEY not in text
    assert "inject" not in text
    assert "FLEETENT_AGENT_SUPPORT_BOT_SLACK_BOT" not in text
