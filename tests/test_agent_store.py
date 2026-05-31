import contextlib

import pytest

import fleetent.agent_store as agent_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_store, "DB_PATH", tmp_path / "users.db")
    import fleetent.user_store as user_store

    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    agent_store._init_db()
    return tmp_path / "users.db"


def test_create_and_get_agent(db):
    agent_store.create_agent("assistant", "You are helpful.", ["shell", "github__*"])
    found = agent_store.get_by_name("assistant")
    assert found is not None
    assert found.name == "assistant"
    assert found.system_prompt == "You are helpful."
    assert found.allowed_tools == ["shell", "github__*"]


def test_get_by_name_missing(db):
    assert agent_store.get_by_name("nonexistent") is None


def test_duplicate_name_raises(db):
    agent_store.create_agent("assistant", "p1", ["shell"])
    with pytest.raises(Exception, match="UNIQUE constraint"):
        agent_store.create_agent("assistant", "p2", ["shell"])


def test_assign_and_get_agent_for_user(db):
    agent = agent_store.create_agent("assistant", "prompt", ["shell"])
    agent_store.assign_user("user-1", agent.id)
    found = agent_store.get_agent_for_user("user-1")
    assert found is not None
    assert found.id == agent.id


def test_get_agent_for_user_unassigned(db):
    assert agent_store.get_agent_for_user("user-99") is None


# --- channel_agents tests ---


def test_assign_and_get_agent_for_channel(db):
    agent = agent_store.create_agent("ch-agent", "Channel prompt.", [])
    agent_store.assign_channel("slack", "C123", agent.id)
    found = agent_store.get_agent_for_channel("slack", "C123")
    assert found is not None
    assert found.id == agent.id


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


# --- default agent tests ---


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


def test_agent_features_null_row_falls_back_to_empty(db):
    import fleetent.user_store as user_store

    # Simulate a row written before the features column carried a value (NULL).
    agent_store.create_agent("a3", "p", ["shell"])
    with user_store._conn() as conn:
        conn.execute("UPDATE agents SET features = NULL WHERE name = ?", ("a3",))
    found = agent_store.get_by_name("a3")
    assert found is not None
    assert found.features == {}


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
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "002_add_agent_features.py"
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
    assert migration.revision == "002"
    assert migration.down_revision == "001"

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
