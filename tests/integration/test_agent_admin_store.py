"""Tests for agent_admin_store (migration 015) + agent_templates."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent.platform.agent_management_console import agent_admin_store as store
from fleetent.platform.agent_management_console import agent_templates


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
    assert "agent_admin_state" in tables


def test_default_state(store_db):
    s = store.get_state("never")
    assert s["status"] == "enabled"
    assert s["provenance"] == "adhoc"
    assert s["drift"] == 0


def test_enable_disable(store_db):
    store.disable("ops")
    assert store.get_state("ops")["status"] == "disabled"
    store.enable("ops")
    assert store.get_state("ops")["status"] == "enabled"


def test_archive_records_timestamp_and_restore(store_db):
    store.archive("ops")
    s = store.get_state("ops")
    assert s["status"] == "archived" and s["archived_at"] is not None
    store.restore("ops")
    assert store.get_state("ops")["status"] == "enabled"


def test_status_rejects_unknown(store_db):
    with pytest.raises(ValueError):
        store.set_status("ops", "bogus")


def test_drift_only_for_managed(store_db):
    store.mark_drift("adhoc-agent")  # adhoc → no-op
    assert store.get_state("adhoc-agent")["drift"] == 0
    store.set_provenance("managed-agent", "managed")
    store.mark_drift("managed-agent")
    assert store.get_state("managed-agent")["drift"] == 1
    store.clear_drift("managed-agent")
    assert store.get_state("managed-agent")["drift"] == 0


def test_list_excludes_archived(store_db):
    store.enable("a")
    store.archive("b")
    visible = {s["agent_name"] for s in store.list_states()}
    assert "a" in visible and "b" not in visible


def test_references_and_protection(store_db):
    # channel_agents is created by the agent_store legacy bootstrap (not by alembic);
    # create it here so references() can query both binding tables, then insert bindings.
    conn = sqlite3.connect(store_db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS channel_agents "
        "(platform TEXT, channel_id TEXT, agent_id INTEGER, created_at TEXT)"
    )
    conn.execute("INSERT INTO user_agents (user_id, agent_id) VALUES ('u1', 7)")
    conn.execute(
        "INSERT INTO channel_agents (platform, channel_id, agent_id, created_at) "
        "VALUES ('slack', 'C1', 7, '2026-01-01')"
    )
    conn.commit()
    conn.close()
    refs = store.references(7)
    assert refs["users"] == ["u1"]
    assert refs["channels"] == ["slack:C1"]
    assert store.is_referenced(7) is True
    assert store.is_referenced(999) is False


def test_templates_readonly():
    templates = {t["id"] for t in agent_templates.list_templates()}
    assert {"readonly-qa", "ops", "support"} <= templates
    t = agent_templates.get_template("ops")
    assert "allowed_tools" in t and "system_prompt" in t
    # mutating the returned copy must not affect the source
    t["allowed_tools"].append("x")
    assert "x" not in agent_templates.get_template("ops")["allowed_tools"]
