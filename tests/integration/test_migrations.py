import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

# Re-exported so the many `from tests.integration.test_migrations import apply_migrations`
# call sites get the shared, process-cached helper unchanged.
from tests.integration._migration_template import apply_migrations

# Absolute so tests that chdir (e.g. test_server) still find the scripts.
_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")

__all__ = ["apply_migrations", "downgrade_migrations"]

_REMOVED_AGENT_KB_TABLE = "knowledge_base_agent_bindings"
_LEGACY_CHANNEL_BINDINGS_TABLE = "channel" + "_agents"
_REMOVED_KB_TABLES = {
    "knowledge_bases",
    "knowledge_documents",
    "knowledge_chunks",
    "knowledge_chunks_fts",
    "knowledge_source_states",
    "knowledge_connector_status",
    "kb_extraction_runs",
    "kb_entities",
    "kb_entity_mentions",
    "kb_relations",
}
_RESIDUAL_MANAGEMENT_TABLES = {
    "shared_memory_items",
    "memory_maintenance_proposals",
    "skill_proposals",
    "skill_hits",
}


def downgrade_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.downgrade(cfg, "base")


def _migration_config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def test_upgrade_creates_tables(tmp_path):
    db = tmp_path / "test.db"
    _upgrade_to(db, "head")
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "im_users" in tables
    assert "agents" in tables
    assert "user_agents" in tables
    # approvals dropped from management DB (agent-owned-approvals, 3b-4):
    # now lives in agent_state.db via per-agent MIGRATIONS v12.
    assert "approvals" not in tables
    # scheduled_tasks dropped from the management DB (agent-owned-scheduled-tasks):
    # it is now a pure agent-side table created only by schedule_store.ensure_schema.
    assert "scheduled_tasks" not in tables
    assert _RESIDUAL_MANAGEMENT_TABLES.isdisjoint(tables)
    assert _REMOVED_AGENT_KB_TABLE not in tables
    assert _REMOVED_KB_TABLES.isdisjoint(tables)
    assert {"traces", "memory_items", "reflection_reports"}.isdisjoint(tables)


def test_head_drops_kb_reflection_reports_and_downgrade_restores_it(tmp_path):
    db = tmp_path / "test.db"
    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "kb_reflection_reports" not in tables
    finally:
        conn.close()

    command.downgrade(_migration_config(db), "074")

    conn = sqlite3.connect(db)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "kb_reflection_reports" in tables
    finally:
        conn.close()


def test_upgrade_does_not_create_trace_indexes_in_management_db(tmp_path):
    db = tmp_path / "test.db"
    _upgrade_to(db, "head")
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "traces" not in tables


def test_upgrade_does_not_create_memory_item_indexes_in_management_db(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "memory_items" not in tables


def test_upgrade_does_not_create_kb_tables_in_management_db(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert _REMOVED_KB_TABLES.isdisjoint(tables)


def test_head_schema_does_not_contain_residual_management_tables(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert _RESIDUAL_MANAGEMENT_TABLES.isdisjoint(tables)


def test_head_schema_contains_blocked_registrations_with_expected_columns(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {row[1] for row in conn.execute("PRAGMA table_info(blocked_registrations)")}
    conn.close()

    assert "blocked_registrations" in tables
    assert cols >= {"email", "reason", "batch_id", "created_at"}


def test_head_onboards_existing_blocked_registrations_table_without_data_loss(tmp_path):
    db = tmp_path / "test.db"
    _upgrade_to(db, "077")
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE blocked_registrations (
            email      TEXT PRIMARY KEY,
            reason     TEXT,
            batch_id   TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO blocked_registrations (email, reason, batch_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        ("blocked@example.com", "seeded", "batch-1", "2026-06-11T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    _upgrade_to(db, "head")

    conn = sqlite3.connect(db)
    row = conn.execute(
        """
        SELECT email, reason, batch_id, created_at
        FROM blocked_registrations
        WHERE email = ?
        """,
        ("blocked@example.com",),
    ).fetchone()
    conn.close()

    assert row == ("blocked@example.com", "seeded", "batch-1", "2026-06-11T00:00:00+00:00")


def test_upgrade_does_not_create_knowledge_base_fts_index(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    fts_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'knowledge_chunks_fts'"
    ).fetchone()
    conn.close()

    assert fts_sql is None


def test_downgrade_removes_tables(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    downgrade_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "im_users" not in tables
    assert "agents" not in tables


def test_upgrade_with_existing_users_table(tmp_path):
    db = tmp_path / "test.db"
    # Simulate the legacy _init_db() creating users table first
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        api_key TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()
    # Migration should not fail even when users table already exists
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "im_users" in tables


def test_column_structure(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)

    # im_users columns
    im_cols = {row[1] for row in conn.execute("PRAGMA table_info(im_users)")}
    assert im_cols >= {"id", "platform", "platform_user_id", "user_id", "created_at"}

    # agents columns
    agent_cols = {row[1] for row in conn.execute("PRAGMA table_info(agents)")}
    assert agent_cols >= {"id", "name", "system_prompt", "allowed_tools", "created_at"}

    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert _RESIDUAL_MANAGEMENT_TABLES.isdisjoint(tables)
    assert _REMOVED_KB_TABLES.isdisjoint(tables)
    assert {"traces", "memory_items", "reflection_reports"}.isdisjoint(tables)


def test_management_db_does_not_define_memory_items_namespace(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "memory_items" not in tables


def test_downgrade_keeps_runtime_tables_out_of_management_db(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    downgrade_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "memory_items" not in tables


def _upgrade_to(db_path: Path, revision: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, revision)


def _downgrade_to(db_path: Path, revision: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.downgrade(cfg, revision)


def test_agent_versions_table_and_columns(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    av_cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_versions)")}
    agent_cols = {row[1] for row in conn.execute("PRAGMA table_info(agents)")}
    conn.close()
    assert "agent_versions" in tables
    assert _LEGACY_CHANNEL_BINDINGS_TABLE not in tables
    assert av_cols >= {
        "id",
        "agent_id",
        "version",
        "system_prompt",
        "allowed_tools",
        "skills_dir",
        "mcp_server_ids",
        "model_overrides",
        "memory_namespace",
        "created_at",
    }
    assert "active_version_id" in agent_cols


def test_agent_v1_backfill_for_existing_rows(tmp_path):
    db = tmp_path / "test.db"
    _upgrade_to(db, "032")
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO agents (name, system_prompt, allowed_tools, created_at)
        VALUES ('legacy', 'You are legacy.', '["shell"]', '2026-01-01T00:00:00+00:00')
        """
    )
    conn.commit()
    agent_id = conn.execute("SELECT id FROM agents WHERE name='legacy'").fetchone()[0]
    conn.close()

    _upgrade_to(db, "033")

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    version = conn.execute("SELECT * FROM agent_versions WHERE agent_id=?", (agent_id,)).fetchone()
    n_versions = conn.execute(
        "SELECT COUNT(*) FROM agent_versions WHERE agent_id=?", (agent_id,)
    ).fetchone()[0]
    conn.close()

    assert agent["active_version_id"] == version["id"]
    assert version["version"] == 1
    assert version["system_prompt"] == "You are legacy."
    assert version["allowed_tools"] == '["shell"]'
    assert version["mcp_server_ids"] is None
    assert version["memory_namespace"] == "default"
    assert n_versions == 1


def test_agent_versions_template_id_dropped_at_head(tmp_path):
    # The template module was removed (migration 049): no template_id column at head,
    # and the agent_templates table is gone.
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    av_cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_versions)")}
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "template_id" not in av_cols
    assert "agent_templates" not in tables


def test_downgrade_removes_template_id_column(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.downgrade(cfg, "034")
    conn = sqlite3.connect(db)
    av_cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_versions)")}
    conn.close()
    assert "template_id" not in av_cols


def test_approvals_not_in_management_db_after_upgrade(tmp_path):
    """approvals table must NOT exist in the management DB after upgrade head (3b-4).

    approvals is now agent-owned (agent_state.db via per-agent MIGRATIONS v12).
    The alembic management-DB definition is a dropped orphan; once migration 073
    runs, this table must be absent from the management DB.
    """
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "approvals" not in tables, (
        "approvals must not exist in the management DB after upgrade head; "
        "it is now owned by agent_state.db (per-agent MIGRATIONS v12)"
    )


def test_agent_runtime_tables_not_in_management_db_after_upgrade(tmp_path):
    """agent_state-owned runtime tables must be absent from the management DB."""
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()

    unexpected = {"traces", "memory_items", "reflection_reports"} & tables
    assert not unexpected, (
        "agent runtime tables must not exist in the management DB after upgrade head; "
        f"found unexpected tables: {sorted(unexpected)}"
    )


def test_downgrade_recreates_agent_runtime_tables_in_management_db(tmp_path):
    """Downgrading below 074 recreates the dropped empty compatibility tables."""
    db = tmp_path / "test.db"
    apply_migrations(db)

    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.downgrade(cfg, "073")

    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    traces_cols = {row[1] for row in conn.execute("PRAGMA table_info(traces)")}
    memory_cols = {row[1] for row in conn.execute("PRAGMA table_info(memory_items)")}
    reflection_cols = {row[1] for row in conn.execute("PRAGMA table_info(reflection_reports)")}
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()

    assert {"traces", "memory_items", "reflection_reports"} <= tables
    assert traces_cols == {
        "id",
        "run_id",
        "span_id",
        "parent_span_id",
        "session_id",
        "user_id",
        "agent_id",
        "tenant_id",
        "event_type",
        "ts",
        "payload_json",
    }
    assert memory_cols == {
        "id",
        "user_id",
        "type",
        "content",
        "created_at",
        "updated_at",
        "expires_at",
    }
    assert reflection_cols == {
        "id",
        "scope",
        "time_window_start",
        "time_window_end",
        "findings_json",
        "created_at",
    }
    assert {
        "idx_traces_run_id",
        "idx_traces_user_ts",
        "idx_traces_agent_ts",
        "idx_traces_tenant_event_ts",
        "idx_memory_items_user_type",
        "idx_memory_items_user_expires",
        "idx_reflection_reports_scope_created",
    } <= indexes


def test_agent_mcp_server_bindings_table_created(tmp_path):
    # The binding table is now agent_mcp_servers; the renamed registry table is mcp_servers.
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_mcp_servers)")}
    conn.close()
    assert "agent_mcp_servers" in tables
    assert cols >= {"agent_id", "server_id", "created_at", "created_by"}


def test_downgrade_removes_agent_mcp_server_bindings_table(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.downgrade(cfg, "040")
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "mcp_servers" not in tables
    assert "agent_mcp_servers" in tables


def test_downgrade_removes_agent_versions(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    downgrade_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "agent_versions" not in tables
    assert "agents" not in tables


def test_downgrade_recreates_kb_entity_unique_key(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    _downgrade_to(db, "074")
    conn = sqlite3.connect(db)
    indexes = conn.execute("PRAGMA index_list(kb_entities)").fetchall()
    unique_indexes = [row[1] for row in indexes if row[2]]
    indexed_columns = {
        index_name: [
            column[2] for column in conn.execute(f"PRAGMA index_info({index_name})").fetchall()
        ]
        for index_name in unique_indexes
    }
    conn.close()

    assert [
        "tenant_id",
        "kb_id",
        "entity_type",
        "normalized_name",
    ] in indexed_columns.values()


def test_connectors_has_agent_id_column(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(connectors)")}
    conn.close()
    assert "agent_id" in cols


def test_agent_mcp_servers_table_and_columns(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {row[1] for row in conn.execute("PRAGMA table_info(mcp_servers)")}
    conn.close()
    assert "mcp_servers" in tables
    assert cols >= {
        "id",
        "agent_id",
        "server_id",
        "transport",
        "url",
        "auth_type",
        "api_key_env",
        "command",
        "args",
        "env",
        "created_at",
    }


def test_connectors_agent_id_nullable_for_existing_rows(tmp_path):
    db = tmp_path / "test.db"
    _upgrade_to(db, "033")
    conn = sqlite3.connect(db)
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO connectors (id, display_name, protocol, enabled, created_at, updated_at)
        VALUES ('github', 'GitHub', 'oauth2', 1, ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    conn.close()

    _upgrade_to(db, "040")

    conn = sqlite3.connect(db)
    agent_id = conn.execute("SELECT agent_id FROM connectors WHERE id='github'").fetchone()[0]
    conn.close()
    assert agent_id is None


def test_downgrade_removes_agent_scoped_connector_schema(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    _downgrade_to(db, "033")
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connector_cols = {row[1] for row in conn.execute("PRAGMA table_info(connectors)")}
    conn.close()
    assert "mcp_servers" not in tables
    assert "agent_id" not in connector_cols


def test_schedule_store_is_agent_owned_self_init():
    """agent-owned-scheduled-tasks: schedule_store is injection-based (set_state_db).
    The DDL lives in agent_state_migrations.py (v27), not in schedule_store itself.
    Uses named params (no ``?``) and does not hand-roll column migrations."""
    schedule_source = Path("src/fleetent/schedule_store.py").read_text()
    migrations_source = Path("src/fleetent/runtime/agent_state_migrations.py").read_text()
    runtime_source = Path("src/fleetent/db.py").read_text()

    # DDL has moved to agent_state_migrations.py v27; schedule_store is DDL-free.
    assert "CREATE TABLE IF NOT EXISTS" not in schedule_source
    assert "set_state_db" in schedule_source, "schedule_store must expose injection interface"
    assert "PRAGMA table_info" not in schedule_source
    assert "?" not in schedule_source
    # The DDL lives in agent_state_migrations.py.
    assert "scheduled_tasks" in migrations_source
    # db.py stays a pure runtime boundary (no schema lifecycle).
    assert "CREATE TABLE IF NOT EXISTS" not in runtime_source
    assert "PRAGMA table_info" not in runtime_source


def test_knowledge_base_store_uses_database_boundary_and_named_parameters():
    store_source = Path("src/fleetent/knowledge_base/store.py").read_text()

    assert "sqlite3.connect" not in store_source
    assert "DB_PATH" not in store_source
    assert "CREATE TABLE" not in store_source
    assert "?" not in store_source
    assert ":tenant_id" in store_source


def test_agent_oauth_bindings_table_and_columns(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_oauth_bindings)")}
    conn.close()
    assert "agent_oauth_bindings" in tables
    assert cols >= {"agent_id", "connector_id", "created_at", "created_by"}
