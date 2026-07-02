"""Integration test: migration 115 — create skill_git_source table.

Verifies that upgrading to head creates the unified external-git-source config /
sync-state table with the expected columns and server-side defaults. The table is a
single-row (id='default') config store for the GitOps inbound sync (and the later
outbound backflow change reuses branch_prefix / auto_open_pr).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

_EXPECTED_COLUMNS = {
    "id",
    "enabled",
    "provider",
    "base_url",
    "project",
    "repo",
    "remote_url",
    "branch",
    "branch_prefix",
    "auto_open_pr",
    "username_env",
    "token_env",
    "webhook_secret_env",
    "sync_interval_seconds",
    "last_synced_commit",
    "last_sync_at",
    "last_sync_error",
}


def _run_migrations(db_path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def test_skill_git_source_table_created(tmp_path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db)

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        inspector = sa.inspect(engine)
        assert inspector.has_table("skill_git_source")
        cols = {col["name"] for col in inspector.get_columns("skill_git_source")}
        assert cols >= _EXPECTED_COLUMNS, f"missing columns: {_EXPECTED_COLUMNS - cols}"
    finally:
        engine.dispose()


def test_skill_git_source_single_row_defaults(tmp_path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db)

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO skill_git_source (id) VALUES ('default')"))
            row = conn.execute(
                sa.text(
                    "SELECT id, enabled, provider, branch, branch_prefix "
                    "FROM skill_git_source WHERE id = 'default'"
                )
            ).fetchone()
        assert row is not None
        assert row[0] == "default"
        assert row[1] == 0  # enabled defaults off
        assert row[2] == "bitbucket"  # provider default
        assert row[3] == "main"  # branch default
        assert row[4] == "backflow"  # branch_prefix default
    finally:
        engine.dispose()
