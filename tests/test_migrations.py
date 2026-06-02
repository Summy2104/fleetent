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
    assert agent_cols >= {
        "id",
        "name",
        "system_prompt",
        "allowed_tools",
        "allowed_skills",
        "created_at",
    }

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
    conn.close()
