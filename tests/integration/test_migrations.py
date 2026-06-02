import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def downgrade_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.downgrade(cfg, "base")


def test_upgrade_creates_tables(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "im_users" in tables
    assert "agents" in tables
    assert "user_agents" in tables
    assert "approvals" in tables
    assert "scheduled_tasks" in tables
    assert "traces" in tables
    assert "memory_items" in tables
    assert "reflection_reports" in tables
    assert "memory_maintenance_proposals" in tables
    assert "knowledge_bases" in tables
    assert "knowledge_documents" in tables
    assert "knowledge_chunks" in tables
    assert "knowledge_chunks_fts" in tables
    assert "knowledge_base_agent_bindings" in tables
    assert "knowledge_connector_status" in tables


def test_upgrade_creates_trace_indexes(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(traces)")}
    conn.close()

    assert indexes >= {
        "idx_traces_run_id",
        "idx_traces_user_ts",
        "idx_traces_agent_ts",
        "idx_traces_tenant_event_ts",
    }


def test_upgrade_creates_memory_item_indexes(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(memory_items)")}
    conn.close()

    assert indexes >= {
        "idx_memory_items_user_type",
        "idx_memory_items_user_expires",
    }


def test_upgrade_creates_knowledge_base_fts_index(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    fts_sql = conn.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE name = 'knowledge_chunks_fts'
        """,
    ).fetchone()[0]
    conn.close()

    assert "CREATE VIRTUAL TABLE" in fts_sql
    assert "fts5" in fts_sql.lower()
    assert "chunk_id UNINDEXED" in fts_sql


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

    # approvals columns
    approval_cols = {row[1] for row in conn.execute("PRAGMA table_info(approvals)")}
    assert approval_cols >= {
        "id",
        "session_id",
        "requester_user_id",
        "risk_level",
        "tool_name",
        "tool_args",
        "status",
        "approver_user_id",
        "created_at",
        "resolved_at",
    }

    schedule_cols = {row[1] for row in conn.execute("PRAGMA table_info(scheduled_tasks)")}
    assert schedule_cols >= {
        "id",
        "name",
        "cron_expr",
        "timezone",
        "user_id",
        "agent_name",
        "message",
        "enabled",
        "source",
        "created_at",
    }

    memory_cols = {row[1] for row in conn.execute("PRAGMA table_info(memory_items)")}
    assert memory_cols >= {
        "id",
        "user_id",
        "type",
        "content",
        "created_at",
        "updated_at",
        "expires_at",
    }
    reflection_cols = {row[1] for row in conn.execute("PRAGMA table_info(reflection_reports)")}
    assert reflection_cols >= {
        "id",
        "scope",
        "time_window_start",
        "time_window_end",
        "findings_json",
        "created_at",
    }
    maintenance_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(memory_maintenance_proposals)")
    }
    assert maintenance_cols >= {
        "id",
        "user_id",
        "action",
        "target_memory_ids_json",
        "proposed_content",
        "metadata_patch_json",
        "risk",
        "reason",
        "evidence_ids_json",
        "status",
        "created_at",
        "updated_at",
        "expires_at",
    }

    kb_cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_bases)")}
    assert kb_cols >= {"tenant_id", "kb_id", "created_at"}
    document_cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_documents)")}
    assert document_cols >= {
        "id",
        "tenant_id",
        "kb_id",
        "filename",
        "source",
        "source_url",
        "archived_at",
        "created_at",
    }
    chunk_cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_chunks)")}
    assert chunk_cols >= {
        "id",
        "document_id",
        "tenant_id",
        "kb_id",
        "position",
        "content",
        "created_at",
    }
    conn.close()


def test_migrated_schedule_store_does_not_create_schema():
    schedule_source = Path("src/fleetent/schedule_store.py").read_text()
    runtime_source = Path("src/fleetent/db.py").read_text()

    assert "CREATE TABLE IF NOT EXISTS" not in schedule_source
    assert "PRAGMA table_info" not in schedule_source
    assert "CREATE TABLE IF NOT EXISTS" not in runtime_source
    assert "PRAGMA table_info" not in runtime_source


def test_knowledge_base_store_uses_database_boundary_and_named_parameters():
    store_source = Path("src/fleetent/intelligence/knowledge_base/store.py").read_text()

    assert "sqlite3.connect" not in store_source
    assert "DB_PATH" not in store_source
    assert "CREATE TABLE" not in store_source
    assert "?" not in store_source
    assert ":tenant_id" in store_source
