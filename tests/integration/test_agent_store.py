"""Tests for agent_store on the unified db runtime.

Schema is created by Alembic migrations against a tmp_path database, isolated via
the DATABASE_URL env var (named params, no legacy _init_db / DB_PATH path).
"""

import contextlib
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import fleetent.agent_store as agent_store


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


def test_create_and_get_agent(db):
    agent_store.create_agent("assistant", "You are helpful.", ["shell", "github__*"])
    found = agent_store.get_by_name("assistant")
    assert found is not None
    assert found.name == "assistant"
    assert found.system_prompt == "You are helpful."
    assert found.allowed_tools == ["shell", "github__*"]


def test_create_agent_sets_active_version_v1(db):
    agent = agent_store.create_agent("assistant", "You are helpful.", ["shell"])
    assert agent.active_version_id is not None
    versions = agent_store.list_versions("assistant")
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].is_active is True
    assert versions[0].mcp_server_ids is None
    assert versions[0].model_overrides == {}
    assert versions[0].memory_namespace == "default"


def test_create_agent_with_isolation_fields(db):
    agent_store.create_agent(
        "analyst",
        "You analyze.",
        ["shell"],
        skills_dir="agents/analyst/skills",
        mcp_server_ids=["github"],
        model_overrides={"default": {"model": "x"}},
        memory_namespace="analyst",
    )
    [v1] = agent_store.list_versions("analyst")
    assert v1.skills_dir == "agents/analyst/skills"
    assert v1.mcp_server_ids == ["github"]
    assert v1.model_overrides == {"default": {"model": "x"}}
    assert v1.memory_namespace == "analyst"


def test_agent_carries_active_version_config_fields(db):
    created = agent_store.create_agent(
        "analyst",
        "You analyze.",
        ["shell"],
        skills_dir="agents/analyst/skills",
        mcp_server_ids=["github"],
        model_overrides={"default": {"model": "x"}},
        memory_namespace="analyst",
    )
    assert created.skills_dir == "agents/analyst/skills"
    assert created.mcp_server_ids == ["github"]
    assert created.model_overrides == {"default": {"model": "x"}}
    assert created.memory_namespace == "analyst"
    found = agent_store.get_by_name("analyst")
    assert found.skills_dir == "agents/analyst/skills"
    assert found.mcp_server_ids == ["github"]
    assert found.model_overrides == {"default": {"model": "x"}}
    assert found.memory_namespace == "analyst"


def test_get_by_name_missing(db):
    assert agent_store.get_by_name("nonexistent") is None


def test_duplicate_name_raises(db):
    agent_store.create_agent("assistant", "p1", ["shell"])
    with pytest.raises(ValueError, match="already exists"):
        agent_store.create_agent("assistant", "p2", ["shell"])


def test_assign_and_get_agent_for_user(db):
    agent = agent_store.create_agent("assistant", "prompt", ["shell"])
    agent_store.assign_user("user-1", agent.id)
    found = agent_store.get_agent_for_user("user-1")
    assert found is not None
    assert found.id == agent.id


def test_get_agent_for_user_unassigned(db):
    assert agent_store.get_agent_for_user("user-99") is None


# --- versioning ---


def test_create_version_copies_active_and_overrides_partial(db):
    agent_store.create_agent("assistant", "v1 prompt", ["shell"], memory_namespace="ns1")
    v2 = agent_store.create_version("assistant", system_prompt="v2 prompt")
    assert v2.version == 2
    assert v2.system_prompt == "v2 prompt"
    # unspecified fields copied from active (v1)
    assert v2.allowed_tools == ["shell"]
    assert v2.memory_namespace == "ns1"
    # default activates the new version
    assert agent_store.get_by_name("assistant").system_prompt == "v2 prompt"


def test_create_version_without_activation_keeps_old_active(db):
    agent_store.create_agent("assistant", "v1 prompt", ["shell"])
    agent_store.create_version("assistant", system_prompt="v2 prompt", activate=False)
    assert agent_store.get_by_name("assistant").system_prompt == "v1 prompt"
    versions = agent_store.list_versions("assistant")
    assert [v.version for v in versions] == [2, 1]
    active = [v for v in versions if v.is_active]
    assert len(active) == 1 and active[0].version == 1


def test_activate_version_switches_active(db):
    agent_store.create_agent("assistant", "v1 prompt", ["shell"])
    agent_store.create_version("assistant", system_prompt="v2 prompt")  # active = 2
    agent_store.activate_version("assistant", 1)
    assert agent_store.get_by_name("assistant").system_prompt == "v1 prompt"


def test_list_versions_desc_with_is_active(db):
    agent_store.create_agent("assistant", "v1", ["shell"])
    agent_store.create_version("assistant", system_prompt="v2")
    agent_store.create_version("assistant", system_prompt="v3")
    versions = agent_store.list_versions("assistant")
    assert [v.version for v in versions] == [3, 2, 1]
    assert versions[0].is_active is True
    assert all(v.is_active is False for v in versions[1:])


def test_get_by_name_version_returns_specific(db):
    agent_store.create_agent("assistant", "v1 prompt", ["shell"])
    agent_store.create_version("assistant", system_prompt="v2 prompt")
    v1 = agent_store.get_by_name_version("assistant", 1)
    assert v1 is not None and v1.system_prompt == "v1 prompt"
    assert agent_store.get_by_name_version("assistant", 99) is None


def test_get_by_name_reflects_active_version(db):
    agent_store.create_agent("assistant", "v1 prompt", ["shell", "github__*"])
    agent_store.create_version("assistant", system_prompt="v2 prompt", allowed_tools=["web_search"])
    found = agent_store.get_by_name("assistant")
    assert found.system_prompt == "v2 prompt"
    assert found.allowed_tools == ["web_search"]


# --- agent ownership (tenant_id / team_id) ---


def test_create_agent_defaults_tenant_and_team(db):
    agent = agent_store.create_agent("owned", "prompt", [])
    assert agent.tenant_id == "default"
    assert agent.team_id is None
    found = agent_store.get_by_name("owned")
    assert found is not None
    assert found.tenant_id == "default"
    assert found.team_id is None


def test_create_agent_with_explicit_ownership(db):
    agent = agent_store.create_agent(
        "acme-support", "prompt", [], tenant_id="acme", team_id="support"
    )
    assert agent.tenant_id == "acme"
    assert agent.team_id == "support"
    found = agent_store.get_by_name("acme-support")
    assert found is not None
    assert found.tenant_id == "acme"
    assert found.team_id == "support"


def test_existing_agent_backfills_default_tenant(db):
    # A row inserted without ownership columns (legacy shape) resolves to the
    # migration's tenant_id default and a null team_id. The agent must still carry
    # a v1 version snapshot, exactly as migration 033's backfill produces.
    from fleetent.config import Settings
    from fleetent.db import create_database

    database = create_database(Settings().database_url)
    with database.transaction() as conn:
        agent_id = conn.execute(
            "INSERT INTO agents (name, system_prompt, allowed_tools, created_at)"
            " VALUES (:name, :system_prompt, :allowed_tools, :created_at)",
            {
                "name": "legacy",
                "system_prompt": "p",
                "allowed_tools": "[]",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        ).lastrowid
        version_id = conn.execute(
            "INSERT INTO agent_versions "
            "(agent_id, version, system_prompt, allowed_tools, model_overrides, "
            " memory_namespace, created_at) "
            "VALUES (:aid, 1, 'p', '[]', '{}', 'default', :now)",
            {"aid": agent_id, "now": "2026-01-01T00:00:00+00:00"},
        ).lastrowid
        conn.execute(
            "UPDATE agents SET active_version_id = :vid WHERE id = :aid",
            {"vid": version_id, "aid": agent_id},
        )
    found = agent_store.get_by_name("legacy")
    assert found is not None
    assert found.tenant_id == "default"
    assert found.team_id is None


def test_ownership_survives_user_and_channel_lookup(db):
    agent = agent_store.create_agent("routed", "prompt", [], tenant_id="acme", team_id="support")
    agent_store.assign_user("user-1", agent.id)
    agent_store.assign_channel("slack", "C123", agent.id)
    by_user = agent_store.get_agent_for_user("user-1")
    by_channel = agent_store.get_agent_for_channel("slack", "C123")
    assert by_user is not None and by_user.tenant_id == "acme" and by_user.team_id == "support"
    assert by_channel is not None and by_channel.tenant_id == "acme"


# --- channel_agents tests ---


def test_assign_and_get_agent_for_channel(db):
    agent = agent_store.create_agent("ch-agent", "Channel prompt.", [])
    agent_store.assign_channel("slack", "C123", agent.id)
    found = agent_store.get_agent_for_channel("slack", "C123")
    assert found is not None
    assert found.id == agent.id


def test_assign_channel_records_bound_version(db):
    agent = agent_store.create_agent("ch-agent", "Channel prompt.", [])
    agent_store.assign_channel("slack", "C123", agent.id)
    bound = agent_store.get_channel_bound_version_id("slack", "C123")
    assert bound == agent.active_version_id


def test_get_agent_for_channel_unbound(db):
    assert agent_store.get_agent_for_channel("slack", "C999") is None


def test_assign_channel_upserts_on_duplicate(db):
    a1 = agent_store.create_agent("agent-a", "A", [])
    a2 = agent_store.create_agent("agent-b", "B", [])
    agent_store.assign_channel("slack", "C1", a1.id)
    agent_store.assign_channel("slack", "C1", a2.id)
    found = agent_store.get_agent_for_channel("slack", "C1")
    assert found is not None
    assert found.id == a2.id


def test_unassign_channel(db):
    agent = agent_store.create_agent("rm-agent", "R", [])
    agent_store.assign_channel("telegram", "G42", agent.id)
    agent_store.unassign_channel("telegram", "G42")
    assert agent_store.get_agent_for_channel("telegram", "G42") is None


def test_platform_isolation(db):
    agent = agent_store.create_agent("iso-agent", "I", [])
    agent_store.assign_channel("slack", "C5", agent.id)
    assert agent_store.get_agent_for_channel("telegram", "C5") is None


# --- hard delete ---


def test_delete_agent_removes_agent_and_versions(db):
    from fleetent.config import Settings
    from fleetent.db import create_database

    agent = agent_store.create_agent("doomed", "v1", ["shell"])
    agent_store.create_version("doomed", system_prompt="v2")
    agent_store.create_version("doomed", system_prompt="v3")

    assert agent_store.delete_agent("doomed") is True
    assert agent_store.get_by_name("doomed") is None

    database = create_database(Settings().database_url)
    rows = database.execute(
        "SELECT COUNT(*) AS c FROM agent_versions WHERE agent_id = :aid", {"aid": agent.id}
    ).fetchone()
    assert rows is not None and int(rows["c"]) == 0


def test_delete_agent_unknown_returns_false(db):
    assert agent_store.delete_agent("ghost") is False


# --- default agent ---


def test_get_default_agent_returns_agent_when_configured(db, monkeypatch):
    agent = agent_store.create_agent("basic", "Basic prompt.", [])
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: "basic")
    found = agent_store.get_default_agent()
    assert found is not None
    assert found.id == agent.id


def test_get_default_agent_returns_none_when_not_configured(db, monkeypatch):
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: None)
    assert agent_store.get_default_agent() is None


def test_get_default_agent_returns_none_when_agent_missing(db, monkeypatch):
    monkeypatch.setattr(agent_store, "_get_default_agent_name", lambda: "nonexistent")
    assert agent_store.get_default_agent() is None


def test_agent_features_default_empty(db):
    agent = agent_store.create_agent("a1", "p", ["shell"])
    assert agent.features == {}
    found = agent_store.get_by_name("a1")
    assert found is not None
    assert found.features == {}


def test_agent_features_roundtrip(db):
    agent_store.create_agent("a2", "p", ["shell"], features={"code_execution": True})
    found = agent_store.get_by_name("a2")
    assert found is not None
    assert found.features == {"code_execution": True}


def test_agent_features_null_row_falls_back_to_empty():
    # A legacy row whose features value is NULL (defensive `or "{}"` guard in
    # _parse_caps). Caps are decoded off the agents row independent of versioning;
    # exercise the cap-parsing fallback directly with a dict row.
    caps = agent_store._parse_caps({"features": None, "plugins": None, "allowed_skills": None})
    assert caps["features"] == {}


def test_agent_plugins_default_empty(db):
    agent = agent_store.create_agent("p1", "p", ["shell"])
    assert agent.plugins == []
    found = agent_store.get_by_name("p1")
    assert found is not None
    assert found.plugins == []


def test_agent_plugins_roundtrip(db):
    agent_store.create_agent("p2", "p", ["shell"], plugins=["crm_tools", "billing"])
    found = agent_store.get_by_name("p2")
    assert found is not None
    assert found.plugins == ["crm_tools", "billing"]


def test_agent_plugins_null_row_falls_back_to_empty():
    # A legacy row whose plugins value is NULL (defensive `or "[]"` guard in
    # _parse_caps). The column is NOT NULL with a '[]' backfill, so a real NULL
    # cannot be written; exercise the cap-parsing fallback directly with a dict row.
    caps = agent_store._parse_caps({"features": None, "plugins": None, "allowed_skills": None})
    assert caps["plugins"] == []


def test_agent_allowed_skills_default_empty(db):
    agent = agent_store.create_agent("s1", "p", ["shell"])
    assert agent.allowed_skills == []
    found = agent_store.get_by_name("s1")
    assert found is not None
    assert found.allowed_skills == []


def test_agent_allowed_skills_roundtrip(db):
    agent_store.create_agent("s2", "p", ["shell"], allowed_skills=["weather", "billing"])
    found = agent_store.get_by_name("s2")
    assert found is not None
    assert found.allowed_skills == ["weather", "billing"]


def test_agent_allowed_skills_null_row_falls_back_to_empty():
    # Legacy row predating the allowed_skills column (NULL); the `or "[]"` guard in
    # _parse_caps maps it to []. Empty means no narrowing — backward compatible.
    caps = agent_store._parse_caps({"features": None, "plugins": None, "allowed_skills": None})
    assert caps["allowed_skills"] == []


def test_init_db_create_table_includes_allowed_skills_column(db):
    import sqlite3

    cols = {row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(agents)").fetchall()}
    assert "allowed_skills" in cols


def test_init_db_create_table_includes_plugins_column(db):
    import sqlite3

    cols = {row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(agents)").fetchall()}
    assert "plugins" in cols


def test_init_db_create_table_includes_features_column(db):
    """New / test DBs go through CREATE TABLE which already carries `features`.

    Per the zy override the runtime ALTER/PRAGMA migration is replaced by alembic
    002; `_init_db` therefore creates the column directly so fresh and test
    databases never lack it (`row[features]` cannot go out of bounds).
    """
    import sqlite3

    cols = {row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(agents)").fetchall()}
    assert "features" in cols


def _load_migration_002():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        # Rebased 002 -> 036 when the duplicate-revision branches were linearized.
        / "036_add_agent_features.py"
    )
    spec = importlib.util.spec_from_file_location("migration_002", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_alembic_002_upgrade_adds_features_to_legacy_table(tmp_path):
    """Alembic 002 adds `features` to a pre-existing (legacy) agents table.

    Drives the migration's upgrade()/downgrade() against a real SQLite legacy
    table (no features column) via alembic Operations bound to a MigrationContext,
    exercising the same op.add_column / op.drop_column the production upgrade runs.
    """
    import sqlite3

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    migration = _load_migration_002()
    # Linearized chain: 002 -> 036, chained after 035 (agent_versions.template_id).
    assert migration.revision == "036"
    assert migration.down_revision == "035"

    dbp = tmp_path / "legacy.db"
    raw = sqlite3.connect(dbp)
    raw.execute(
        """CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            system_prompt TEXT NOT NULL,
            allowed_tools TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    raw.commit()
    raw.close()

    engine = sa.create_engine(f"sqlite:///{dbp}")

    def _columns() -> set[str]:
        return {r[1] for r in sqlite3.connect(dbp).execute("PRAGMA table_info(agents)").fetchall()}

    assert "features" not in _columns()

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        ops = Operations(ctx)
        with _patched_op(migration, ops):
            migration.upgrade()
    assert "features" in _columns()

    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        ops = Operations(ctx)
        with _patched_op(migration, ops):
            migration.downgrade()
    assert "features" not in _columns()


@contextlib.contextmanager
def _patched_op(migration, ops):
    """Bind the migration module's `op` proxy to a concrete Operations instance."""
    saved = migration.op
    migration.op = ops
    try:
        yield ops
    finally:
        migration.op = saved
