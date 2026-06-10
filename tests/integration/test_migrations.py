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


def downgrade_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
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
    # approvals dropped from management DB (agent-owned-approvals, 3b-4):
    # now lives in agent_state.db via per-agent MIGRATIONS v12.
    assert "approvals" not in tables
    # scheduled_tasks dropped from the management DB (agent-owned-scheduled-tasks):
    # it is now a pure agent-side table created only by schedule_store.ensure_schema.
    assert "scheduled_tasks" not in tables
    assert "traces" in tables
    assert "memory_items" in tables
    assert "reflection_reports" in tables
    assert "memory_maintenance_proposals" in tables
    assert "knowledge_bases" in tables
    assert "knowledge_documents" in tables
    assert "knowledge_chunks" in tables
    assert "knowledge_chunks_fts" in tables
    assert _REMOVED_AGENT_KB_TABLE not in tables
    assert "knowledge_connector_status" in tables
    assert "kb_extraction_runs" in tables
    assert "kb_entities" in tables
    assert "kb_entity_mentions" in tables
    assert "kb_relations" in tables
    assert "kb_reflection_reports" in tables
    assert "skill_proposals" in tables
    assert "shared_memory_items" in tables


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
    shared_memory_cols = {row[1] for row in conn.execute("PRAGMA table_info(shared_memory_items)")}
    assert shared_memory_cols >= {
        "id",
        "scope_type",
        "scope_id",
        "type",
        "content",
        "status",
        "source",
        "source_ref",
        "created_by",
        "created_at",
        "updated_at",
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
    extraction_run_cols = {row[1] for row in conn.execute("PRAGMA table_info(kb_extraction_runs)")}
    assert extraction_run_cols >= {
        "id",
        "tenant_id",
        "kb_id",
        "document_id",
        "extractor",
        "status",
        "started_at",
        "finished_at",
        "documents_scanned",
        "chunks_scanned",
        "entities_upserted",
        "mentions_written",
        "relations_written",
        "failed_count",
        "error_summary",
        "metadata_json",
    }
    kb_reflection_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(kb_reflection_reports)")
    }
    assert kb_reflection_cols >= {
        "id",
        "scope",
        "time_window_start",
        "time_window_end",
        "findings_json",
        "signal_summary_json",
        "created_at",
    }
    skill_proposal_cols = {row[1] for row in conn.execute("PRAGMA table_info(skill_proposals)")}
    assert skill_proposal_cols >= {
        "id",
        "type",
        "target_skill",
        "reason",
        "evidence_refs_json",
        "risk_level",
        "suggested_draft",
        "suggested_diff",
        "status",
        "reviewer_user_id",
        "reviewed_at",
        "rejection_reason",
        "actor_user_id",
        "applied_at",
        "created_at",
        "updated_at",
    }
    entity_cols = {row[1] for row in conn.execute("PRAGMA table_info(kb_entities)")}
    assert entity_cols >= {
        "id",
        "tenant_id",
        "kb_id",
        "entity_type",
        "name",
        "normalized_name",
        "metadata_json",
        "created_at",
        "updated_at",
    }
    mention_cols = {row[1] for row in conn.execute("PRAGMA table_info(kb_entity_mentions)")}
    assert mention_cols >= {
        "id",
        "entity_id",
        "tenant_id",
        "kb_id",
        "document_id",
        "chunk_id",
        "text",
        "confidence",
        "extraction_run_id",
        "created_at",
    }
    relation_cols = {row[1] for row in conn.execute("PRAGMA table_info(kb_relations)")}
    assert relation_cols >= {
        "id",
        "tenant_id",
        "kb_id",
        "relation_type",
        "source_entity_id",
        "target_entity_id",
        "evidence_document_id",
        "evidence_chunk_id",
        "evidence_text",
        "confidence",
        "extraction_run_id",
        "created_at",
    }
    conn.close()


def test_memory_items_has_namespace_column(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(memory_items)")}
    conn.close()
    assert "namespace" in cols


def test_memory_namespace_server_default_backfills_existing_rows(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    now = "2026-01-01T00:00:00+00:00"
    # Insert without specifying namespace: server default must apply.
    conn.execute(
        """
        INSERT INTO memory_items (id, user_id, type, content, created_at, updated_at)
        VALUES ('m1', 'u1', 'identity', 'fact', ?, ?)
        """,
        (now, now),
    )
    conn.commit()
    namespace = conn.execute("SELECT namespace FROM memory_items WHERE id = 'm1'").fetchone()[0]
    conn.close()
    assert namespace == "default"


def test_downgrade_removes_namespace_column(tmp_path):
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
    chan_cols = {row[1] for row in conn.execute("PRAGMA table_info(channel_agents)")}
    conn.close()
    assert "agent_versions" in tables
    assert "channel_agents" in tables
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
    assert "bound_version_id" in chan_cols


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


def test_agent_mcp_server_bindings_table_created(tmp_path):
    # The binding table (agent->global server join) is distinct from the
    # full-definition agent_mcp_servers table; both must exist at head.
    db = tmp_path / "test.db"
    apply_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_mcp_server_bindings)")}
    conn.close()
    assert "agent_mcp_server_bindings" in tables
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
    assert "agent_mcp_server_bindings" not in tables


def test_downgrade_removes_agent_versions(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
    downgrade_migrations(db)
    conn = sqlite3.connect(db)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "agent_versions" not in tables
    assert "agents" not in tables


def test_knowledge_entity_unique_key_is_scoped(tmp_path):
    db = tmp_path / "test.db"
    apply_migrations(db)
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
    cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_mcp_servers)")}
    conn.close()
    assert "agent_mcp_servers" in tables
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
    assert "agent_mcp_servers" not in tables
    assert "agent_id" not in connector_cols


def test_schedule_store_is_agent_owned_self_init():
    """agent-owned-scheduled-tasks: schedule_store joins the agent-side dual-authority
    tables — it self-creates via ensure_schema (CREATE TABLE IF NOT EXISTS), uses named
    params (no ``?``), and does not hand-roll column migrations (no PRAGMA table_info).
    The DDL/alembic-head consistency is enforced by test_schema_drift_guard."""
    schedule_source = Path("src/fleetent/schedule_store.py").read_text()
    runtime_source = Path("src/fleetent/db.py").read_text()

    assert "CREATE TABLE IF NOT EXISTS" in schedule_source
    assert "PRAGMA table_info" not in schedule_source
    assert "?" not in schedule_source
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
