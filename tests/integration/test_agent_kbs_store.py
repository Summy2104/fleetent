"""Tests for agent_kbs_store: KB↔Agent binding matrix (migration 012, db runtime)."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent.platform.knowledge_base_management import agent_kbs_store as store


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
    assert "agent_kbs" in tables


def test_bind_and_list_both_directions(store_db):
    store.bind("default", "sales", "agent-a", created_by="admin")
    store.bind("default", "sales", "agent-b", created_by="admin")
    store.bind("default", "support", "agent-a", created_by="admin")
    assert store.list_agents_for_kb("default", "sales") == ["agent-a", "agent-b"]
    assert store.list_kbs_for_agent("default", "agent-a") == ["sales", "support"]


def test_bind_is_idempotent(store_db):
    store.bind("default", "sales", "agent-a")
    store.bind("default", "sales", "agent-a")  # no error, no dup
    assert store.list_agents_for_kb("default", "sales") == ["agent-a"]


def test_is_kb_bound(store_db):
    assert store.is_kb_bound("default", "sales") is False
    store.bind("default", "sales", "agent-a")
    assert store.is_kb_bound("default", "sales") is True


def test_unbind(store_db):
    store.bind("default", "sales", "agent-a")
    store.unbind("default", "sales", "agent-a")
    assert store.is_kb_bound("default", "sales") is False


def test_tenancy_isolation(store_db):
    store.bind("t1", "sales", "agent-a")
    assert store.is_kb_bound("t2", "sales") is False
    assert store.list_agents_for_kb("t2", "sales") == []
