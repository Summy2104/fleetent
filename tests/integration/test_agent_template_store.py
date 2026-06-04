"""Tests for agent_template_store on the unified db runtime.

Schema is created by Alembic migrations against a tmp_path database, isolated via
the DATABASE_URL env var (named params, no legacy _init_db / DB_PATH path).
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import fleetent.platform.agent_management_console.agent_template_store as tmpl_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_migration_seeds_builtins(db):
    by_id = {t["id"]: t for t in tmpl_store.list_templates()}
    assert {"readonly-qa", "ops", "support"} <= set(by_id)
    assert by_id["ops"]["display_name"] == "运维 Agent"
    assert by_id["ops"]["allowed_tools"] == ["read_*", "exec_*", "github__*"]
    assert "operations assistant" in by_id["ops"]["system_prompt"]


def test_create_persists(db):
    tmpl_store.create_template("triage", "Triage", ["read_*"], "You triage.")
    t = tmpl_store.get_template("triage")
    assert t is not None
    assert t["display_name"] == "Triage"
    assert t["allowed_tools"] == ["read_*"]
    assert t["system_prompt"] == "You triage."


def test_create_duplicate_raises(db):
    with pytest.raises(ValueError):
        tmpl_store.create_template("ops", "Dup", [], "")


def test_update_overrides_only_provided(db):
    before = tmpl_store.get_template("ops")
    tmpl_store.update_template("ops", system_prompt="v2")
    after = tmpl_store.get_template("ops")
    assert after["system_prompt"] == "v2"
    assert after["allowed_tools"] == before["allowed_tools"]


def test_update_missing_returns_falsey(db):
    assert not tmpl_store.update_template("nope", system_prompt="x")


def test_delete_removes(db):
    assert tmpl_store.delete_template("support") is True
    assert tmpl_store.get_template("support") is None


def test_delete_missing_returns_false(db):
    assert tmpl_store.delete_template("nope") is False
