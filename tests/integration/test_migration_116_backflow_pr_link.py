"""Integration test: migration 116 — add PR-link columns to backflow_proposals.

Verifies upgrading to head adds the nullable PR-tracking columns the outbound backflow
sweep / governance writes (branch / pr id / url / state / target / merge commit), that they
default NULL on existing rows, and that they are writable.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

_PR_COLUMNS = {"pr_id", "pr_branch", "pr_url", "pr_state", "pr_target_branch", "pr_merge_commit"}


def _run_migrations(db_path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def test_backflow_pr_columns_added(tmp_path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db)

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        inspector = sa.inspect(engine)
        assert inspector.has_table("backflow_proposals")
        cols = {c["name"] for c in inspector.get_columns("backflow_proposals")}
        assert cols >= _PR_COLUMNS, f"missing columns: {_PR_COLUMNS - cols}"
    finally:
        engine.dispose()


def test_backflow_pr_columns_default_null_and_writable(tmp_path, monkeypatch) -> None:
    db = tmp_path / "mgmt.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("FLEETENT_HOME", raising=False)

    _run_migrations(db)

    engine = sa.create_engine(f"sqlite:///{db}")
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO backflow_proposals "
                    "(status, agent_id, skill_name, proposed_bundle, created_at, updated_at) "
                    "VALUES ('pending', 1, 'crm-ops', '{}', 'now', 'now')"
                )
            )
            row = conn.execute(
                sa.text(
                    "SELECT pr_id, pr_branch, pr_url, pr_state, pr_target_branch, pr_merge_commit "
                    "FROM backflow_proposals WHERE skill_name = 'crm-ops'"
                )
            ).fetchone()
        assert row is not None
        assert all(value is None for value in row)  # nullable, default NULL on existing rows

        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE backflow_proposals SET pr_branch = :b, pr_state = 'backed_up' "
                    "WHERE skill_name = 'crm-ops'"
                ),
                {"b": "backflow/support-bot/crm-ops"},
            )
            updated = conn.execute(
                sa.text(
                    "SELECT pr_branch, pr_state FROM backflow_proposals "
                    "WHERE skill_name = 'crm-ops'"
                )
            ).fetchone()
        assert updated == ("backflow/support-bot/crm-ops", "backed_up")
    finally:
        engine.dispose()
