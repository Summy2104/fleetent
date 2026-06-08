"""Tests for skill_admin_store: Skill↔Agent bindings + managed/adhoc provenance + drift.

Uses the unified db runtime (named params) with the schema created by Alembic
migrations against a tmp_path database, isolated via the DATABASE_URL env var.
"""

import sqlite3

import pytest

from fleetent.platform.skill_management import skill_admin_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


# --- 2. tables exist + named params + binding ---


def test_migration_creates_tables(store_db):
    conn = sqlite3.connect(store_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "agent_skills" in tables
    assert "skill_provenance" in tables


def test_agent_skills_columns(store_db):
    conn = sqlite3.connect(store_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(agent_skills)")}
    conn.close()
    assert cols >= {"agent_id", "skill_name", "enabled", "updated_at", "updated_by"}


def test_skill_provenance_columns(store_db):
    conn = sqlite3.connect(store_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(skill_provenance)")}
    conn.close()
    assert cols >= {
        "skill_name",
        "source",
        "drift",
        "immutable_fields",
        "last_deploy_at",
        "updated_at",
    }


def test_set_binding_and_list(store_db):
    skill_admin_store.set_binding("agent-a", "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding("agent-b", "summarizer", enabled=False, updated_by="admin")
    agents = skill_admin_store.list_agents_for_skill("summarizer")
    by_id = {a["agent_id"]: a for a in agents}
    assert by_id["agent-a"]["enabled"] == 1
    assert by_id["agent-b"]["enabled"] == 0


def test_set_binding_is_idempotent(store_db):
    skill_admin_store.set_binding("agent-a", "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding("agent-a", "summarizer", enabled=False, updated_by="admin2")
    agents = skill_admin_store.list_agents_for_skill("summarizer")
    assert len(agents) == 1
    assert agents[0]["enabled"] == 0
    assert agents[0]["updated_by"] == "admin2"


def test_list_skills_for_agent(store_db):
    skill_admin_store.set_binding("agent-a", "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding("agent-a", "translator", enabled=True, updated_by="admin")
    names = {s["skill_name"] for s in skill_admin_store.list_skills_for_agent("agent-a")}
    assert names == {"summarizer", "translator"}


def test_agents_enabling_returns_only_enabled(store_db):
    skill_admin_store.set_binding("agent-a", "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding("agent-b", "summarizer", enabled=False, updated_by="admin")
    enabling = skill_admin_store.agents_enabling("summarizer")
    assert enabling == ["agent-a"]


def test_has_any_binding(store_db):
    assert skill_admin_store.has_any_binding("agent-a") is False
    skill_admin_store.set_binding("agent-a", "summarizer", enabled=False, updated_by="admin")
    assert skill_admin_store.has_any_binding("agent-a") is True


def test_enabled_skill_names(store_db):
    skill_admin_store.set_binding("agent-a", "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding("agent-a", "translator", enabled=False, updated_by="admin")
    assert skill_admin_store.enabled_skill_names("agent-a") == {"summarizer"}


# --- 3. provenance + drift ---


def test_set_and_get_provenance(store_db):
    skill_admin_store.set_provenance("summarizer", "adhoc")
    assert skill_admin_store.get_provenance("summarizer")["source"] == "adhoc"
    skill_admin_store.set_provenance("summarizer", "managed")
    assert skill_admin_store.get_provenance("summarizer")["source"] == "managed"


def test_unknown_provenance_defaults_to_adhoc(store_db):
    # UI-created skills with no explicit provenance row are treated as adhoc.
    assert skill_admin_store.get_provenance("never-set")["source"] == "adhoc"
    assert skill_admin_store.get_provenance("never-set")["drift"] == 0


def test_mark_and_clear_drift(store_db):
    skill_admin_store.set_provenance("summarizer", "managed")
    skill_admin_store.mark_drift("summarizer")
    assert skill_admin_store.get_provenance("summarizer")["drift"] == 1
    skill_admin_store.clear_drift("summarizer")
    assert skill_admin_store.get_provenance("summarizer")["drift"] == 0


def test_immutable_field_change_flagged(store_db):
    skill_admin_store.set_provenance("summarizer", "managed", immutable_fields=["name"])
    # changing an immutable field on a managed skill returns a warning flag
    assert skill_admin_store.is_immutable_change("summarizer", {"name"}) is True
    assert skill_admin_store.is_immutable_change("summarizer", {"description"}) is False


def test_adhoc_skill_has_no_immutable_constraint(store_db):
    skill_admin_store.set_provenance("widget", "adhoc")
    assert skill_admin_store.is_immutable_change("widget", {"name"}) is False


# --- management state ---


def test_state_defaults_active_enabled(store_db):
    state = skill_admin_store.get_state("never-set")
    assert state["status"] == "active"
    assert state["global_enabled"] == 1
    assert state["forced"] == 0


def test_set_audit_result_roundtrip(store_db):
    skill_admin_store.set_audit_result("s", "suspicious", rules=["eval(", "os.system"])
    state = skill_admin_store.get_state("s")
    assert state["audit_verdict"] == "suspicious"
    assert "eval(" in state["audit_rules"]


def test_set_status_archive_records_timestamp(store_db):
    skill_admin_store.set_status("s", "archived")
    state = skill_admin_store.get_state("s")
    assert state["status"] == "archived"
    assert state["archived_at"] is not None


def test_global_enable_toggle(store_db):
    skill_admin_store.set_global_enabled("s", False)
    assert skill_admin_store.get_state("s")["global_enabled"] == 0
    skill_admin_store.set_global_enabled("s", True)
    assert skill_admin_store.get_state("s")["global_enabled"] == 1


def test_list_states_excludes_archived_by_default(store_db):
    skill_admin_store.set_global_enabled("active-one", True)
    skill_admin_store.set_status("archived-one", "archived")
    visible = {s["skill_name"] for s in skill_admin_store.list_states()}
    assert "active-one" in visible
    assert "archived-one" not in visible
    allnames = {s["skill_name"] for s in skill_admin_store.list_states(include_archived=True)}
    assert "archived-one" in allnames


def test_set_status_rejects_unknown(store_db):
    with pytest.raises(ValueError):
        skill_admin_store.set_status("s", "bogus")
