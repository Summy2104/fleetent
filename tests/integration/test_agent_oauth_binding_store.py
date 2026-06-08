"""Per-agent OAuth connector binding store (parallels agent MCP binding)."""

import pytest

from fleetent.platform.connector_management import agent_oauth_binding_store as store
from tests.integration._migration_template import apply_migrations


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
