"""Tests for connector_config_store (migration 013, db runtime). Secret never stored."""

import sqlite3

import pytest

from fleetent.platform.connector_management import connector_config_store as store
from tests.integration._migration_template import apply_migrations


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
    assert "connectors" in tables


def test_add_and_get(store_db):
    store.add_connector(
        "gdrive",
        "Google Drive",
        oauth_config={
            "authorize": "https://a",
            "token": "https://t",
            "scopes": ["drive.readonly"],
            "client_id": "cid",
        },
    )
    c = store.get_connector("gdrive")
    assert c["display_name"] == "Google Drive"
    assert c["oauth_config"]["client_id"] == "cid"
    assert c["protocol"] == "oauth2"


def test_client_secret_never_stored(store_db):
    store.add_connector(
        "gh",
        "GitHub",
        oauth_config={"client_id": "cid", "client_secret": "shhh"},
    )
    c = store.get_connector("gh")
    assert "client_secret" not in c["oauth_config"]
    # confirm it's not in the raw row either
    conn = sqlite3.connect(store_db)
    raw = conn.execute("SELECT oauth_config FROM connectors WHERE id='gh'").fetchone()[0]
    conn.close()
    assert "shhh" not in (raw or "")


def test_edit_strips_secret(store_db):
    store.add_connector("gh", "GitHub", oauth_config={"client_id": "cid"})
    store.edit_connector("gh", oauth_config={"client_id": "cid2", "client_secret": "leak"})
    c = store.get_connector("gh")
    assert c["oauth_config"]["client_id"] == "cid2"
    assert "client_secret" not in c["oauth_config"]


def test_list(store_db):
    store.add_connector("a", "A")
    store.add_connector("b", "B")
    assert {c["id"] for c in store.list_connectors()} == {"a", "b"}


def test_same_id_allowed_across_agents(store_db):
    store.add_connector("github", "GH global")
    store.add_connector("github", "GH agent 5", agent_id=5)
    store.add_connector("github", "GH agent 7", agent_id=7)
    assert store.get_connector("github")["display_name"] == "GH global"
    assert store.get_connector("github", agent_id=5)["display_name"] == "GH agent 5"
    assert store.get_connector("github", agent_id=7)["display_name"] == "GH agent 7"


def test_agent_owned_overrides_global_default(store_db):
    store.add_connector("github", "GH global", oauth_config={"client_id": "global"})
    store.add_connector("github", "GH agent 5", oauth_config={"client_id": "scoped"}, agent_id=5)
    resolved = store.get_connector("github", agent_id=5)
    assert resolved["oauth_config"]["client_id"] == "scoped"


def test_get_falls_back_to_global_when_no_agent_row(store_db):
    store.add_connector("github", "GH global")
    resolved = store.get_connector("github", agent_id=5)
    assert resolved["display_name"] == "GH global"


def test_null_scope_returns_only_global_defaults(store_db):
    store.add_connector("github", "GH global")
    store.add_connector("github", "GH agent 5", agent_id=5)
    listed = store.list_connectors()
    assert {(c["id"], c.get("agent_id")) for c in listed} == {("github", None)}


def test_list_scoped_overlays_agent_on_global(store_db):
    store.add_connector("github", "GH global")
    store.add_connector("slack", "Slack global")
    store.add_connector("github", "GH agent 5", agent_id=5)
    listed = {c["id"]: c for c in store.list_connectors(agent_id=5)}
    assert set(listed) == {"github", "slack"}
    assert listed["github"]["display_name"] == "GH agent 5"
    assert listed["slack"]["display_name"] == "Slack global"


def test_duplicate_within_same_agent_scope_rejected(store_db):
    store.add_connector("github", "GH agent 5", agent_id=5)
    with pytest.raises(sqlite3.IntegrityError):
        store.add_connector("github", "GH agent 5 dup", agent_id=5)


def test_duplicate_global_rejected(store_db):
    store.add_connector("github", "GH global")
    with pytest.raises(sqlite3.IntegrityError):
        store.add_connector("github", "GH global dup")


def test_agent_scoped_secret_never_stored(store_db):
    store.add_connector(
        "gh", "GitHub", oauth_config={"client_id": "cid", "client_secret": "shhh"}, agent_id=9
    )
    c = store.get_connector("gh", agent_id=9)
    assert "client_secret" not in c["oauth_config"]


def test_delete_connector_removes_row(store_db):
    store.add_connector("gh", "GitHub")
    store.delete_connector("gh")
    assert store.get_connector("gh") is None


def test_delete_connector_is_scoped(store_db):
    store.add_connector("gh", "global")
    store.add_connector("gh", "agent5", agent_id=5)
    store.delete_connector("gh")  # global scope only
    assert store.get_connector("gh") is None
    # the agent-owned row must survive a global delete
    assert store.get_connector("gh", agent_id=5)["display_name"] == "agent5"
