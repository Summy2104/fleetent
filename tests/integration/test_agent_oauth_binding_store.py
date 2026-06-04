"""Per-agent OAuth connector binding store (parallels agent MCP binding)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent.platform.connector_management import agent_oauth_binding_store as store


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


def test_bind_is_idempotent(store_db):
    store.bind(5, "github")
    store.bind(5, "github")
    assert store.list_connectors_for_agent(5) == ["github"]


def test_unbind_removes(store_db):
    store.bind(5, "github")
    store.unbind(5, "github")
    assert store.list_connectors_for_agent(5) == []


def test_scoped_per_agent(store_db):
    store.bind(5, "github")
    store.bind(7, "github")
    store.bind(5, "jira")
    assert store.list_connectors_for_agent(5) == ["github", "jira"]
    assert sorted(store.list_agents_for_connector("github")) == [5, 7]
