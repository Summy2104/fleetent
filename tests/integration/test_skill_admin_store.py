"""Tests for skill_admin_store: Skill↔Agent bindings + managed/adhoc provenance + drift.

Uses the unified db runtime (named params) with the schema created by Alembic
migrations against a tmp_path database, isolated via the DATABASE_URL env var.
"""

import sqlite3

import pytest

from fleetent import agent_store
from fleetent.platform.skill_management import skill_admin_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_bulk_current_versions_and_resync_epochs(store_db):
    agent = agent_store.create_agent("support", "p", [])
    skill_admin_store.ensure_catalog_entries(["alpha", "beta"])
    skill_admin_store.set_current_version("alpha", "sha-a")
    # beta left without a current_version; gamma has no catalog row at all.
    for name in ("alpha", "beta"):
        skill_admin_store.set_binding(agent.id, name, True, updated_by="admin")
    skill_admin_store.bump_resync_epoch(agent.id, "alpha")

    versions = skill_admin_store.get_current_versions(["alpha", "beta", "gamma"])
    assert versions == {"alpha": "sha-a", "beta": None, "gamma": None}

    epochs = skill_admin_store.get_resync_epochs(agent.id, ["alpha", "beta", "gamma"])
    # alpha bumped to 1; beta bound but never bumped -> 0; gamma unbound -> 0.
    assert epochs == {"alpha": 1, "beta": 0, "gamma": 0}
    assert skill_admin_store.get_current_versions([]) == {}
    assert skill_admin_store.get_resync_epochs(agent.id, []) == {}


# --- 2. tables exist + named params + binding ---


def test_migration_creates_tables(store_db):
    conn = sqlite3.connect(store_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "agent_skills" in tables
    assert "skills" in tables


def test_agent_skills_columns(store_db):
    conn = sqlite3.connect(store_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(agent_skills)")}
    conn.close()
    assert cols >= {"agent_id", "skill_name", "enabled", "updated_at", "updated_by"}


def test_skills_master_columns(store_db):
    conn = sqlite3.connect(store_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(skills)")}
    conn.close()
    assert cols >= {
        "name",
        "status",
        "global_enabled",
        "audit_verdict",
        "audit_rules",
        "forced",
        "source",
        "immutable_fields",
        "current_version",
        "updated_at",
    }


def test_set_binding_and_list(store_db):
    agent_a = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    agent_b = agent_store.create_agent("agent-b", "Prompt.", ["shell"])
    skill_admin_store.set_binding(agent_a.id, "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding(agent_b.id, "summarizer", enabled=False, updated_by="admin")
    agents = skill_admin_store.list_agents_for_skill("summarizer")
    by_id = {a["agent_id"]: a for a in agents}
    assert by_id[agent_a.id]["enabled"] == 1
    assert by_id[agent_b.id]["enabled"] == 0


def test_set_binding_is_idempotent(store_db):
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    skill_admin_store.set_binding(agent.id, "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding(agent.id, "summarizer", enabled=False, updated_by="admin2")
    agents = skill_admin_store.list_agents_for_skill("summarizer")
    assert len(agents) == 1
    assert agents[0]["enabled"] == 0
    assert agents[0]["updated_by"] == "admin2"


def test_list_skills_for_agent(store_db):
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    skill_admin_store.set_binding(agent.id, "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding(agent.id, "translator", enabled=True, updated_by="admin")
    names = {s["skill_name"] for s in skill_admin_store.list_skills_for_agent(agent.id)}
    assert names == {"summarizer", "translator"}


def test_agents_enabling_returns_only_enabled(store_db):
    agent_a = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    agent_b = agent_store.create_agent("agent-b", "Prompt.", ["shell"])
    skill_admin_store.set_binding(agent_a.id, "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding(agent_b.id, "summarizer", enabled=False, updated_by="admin")
    enabling = skill_admin_store.agents_enabling("summarizer")
    assert enabling == [agent_a.id]


def test_has_any_binding(store_db):
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    assert skill_admin_store.has_any_binding(agent.id) is False
    skill_admin_store.set_binding(agent.id, "summarizer", enabled=False, updated_by="admin")
    assert skill_admin_store.has_any_binding(agent.id) is True


def test_enabled_skill_names(store_db):
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    skill_admin_store.set_binding(agent.id, "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding(agent.id, "translator", enabled=False, updated_by="admin")
    assert skill_admin_store.enabled_skill_names(agent.id) == {"summarizer"}


def test_integer_agent_id_crud(store_db):
    agent = agent_store.create_agent("agent-seven", "Prompt.", ["shell"])
    skill_admin_store.set_binding(agent.id, "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding(agent.id, "translator", enabled=False, updated_by="admin")

    agents = skill_admin_store.list_agents_for_skill("summarizer")
    by_id = {a["agent_id"]: a for a in agents}

    assert by_id[agent.id]["enabled"] == 1
    assert {s["skill_name"] for s in skill_admin_store.list_skills_for_agent(agent.id)} == {
        "summarizer",
        "translator",
    }
    assert skill_admin_store.has_any_binding(agent.id) is True
    assert skill_admin_store.enabled_skill_names(agent.id) == {"summarizer"}


# --- 3. skills master table + per-agent drift ---


def test_state_reads_and_writes_skills_master_table(store_db):
    state = skill_admin_store.get_state("never-set")
    assert state["status"] == "active"
    assert state["global_enabled"] == 1

    skill_admin_store.set_global_enabled("summarizer", False)
    skill_admin_store.set_status("summarizer", "quarantined")

    conn = sqlite3.connect(store_db)
    try:
        row = conn.execute(
            "SELECT name, status, global_enabled FROM skills WHERE name = ?",
            ("summarizer",),
        ).fetchone()
    finally:
        conn.close()

    assert row == ("summarizer", "quarantined", 0)


def test_catalog_source_and_binding_upsert_missing_skill_rows(store_db):
    agent = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    skill_admin_store.set_source("summarizer", "managed", immutable_fields=["name"])
    skill_admin_store.set_binding(agent.id, "translator", enabled=True, updated_by="admin")

    assert skill_admin_store.get_source("summarizer") == {
        "skill_name": "summarizer",
        "source": "managed",
        "immutable_fields": '["name"]',
        "current_version": None,
    }
    assert skill_admin_store.get_source("translator") == {
        "skill_name": "translator",
        "source": "adhoc",
        "immutable_fields": None,
        "current_version": None,
    }


def test_per_agent_drift_isolated_by_agent_skill_row(store_db):
    agent_a = agent_store.create_agent("agent-a", "Prompt.", ["shell"])
    agent_b = agent_store.create_agent("agent-b", "Prompt.", ["shell"])
    skill_admin_store.set_binding(agent_a.id, "summarizer", enabled=True, updated_by="admin")
    skill_admin_store.set_binding(agent_b.id, "summarizer", enabled=True, updated_by="admin")

    skill_admin_store.set_drift(agent_a.id, "summarizer", drifted=True)

    assert skill_admin_store.get_drift(agent_a.id, "summarizer")["drift"] == 1
    assert skill_admin_store.get_drift(agent_b.id, "summarizer")["drift"] == 0
    assert skill_admin_store.drifted_agents("summarizer") == [agent_a.id]


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
