"""Single-row persistence for the external git source config + sync state.

Owns the management table ``skill_git_source`` (schema by Alembic 113): one config row
(id='default') binding the skill pool to an external git repo as authoritative source.
Credentials live elsewhere (agent_secrets, env-ref); this table holds only env-ref names,
non-secret config, and last-sync state. Schema lifecycle is owned by Alembic; this module
never creates the table.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteConnection, SQLiteDatabase, create_database

logger = logging.getLogger(__name__)

_ROW_ID = "default"

_CONFIG_COLUMNS = (
    "enabled",
    "provider",
    "base_url",
    "project",
    "repo",
    "remote_url",
    "branch",
    "branch_prefix",
    "skills_subdir",
    "auto_open_pr",
    "username_env",
    "token_env",
    "webhook_secret_env",
    "sync_interval_seconds",
)

_ALL_COLUMNS = (
    "id, enabled, provider, base_url, project, repo, remote_url, branch, "
    "branch_prefix, skills_subdir, auto_open_pr, username_env, token_env, "
    "webhook_secret_env, sync_interval_seconds, last_synced_commit, last_sync_at, "
    "last_sync_error"
)


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _ensure_row(conn: SQLiteConnection) -> None:
    conn.execute(
        "INSERT INTO skill_git_source (id) VALUES (:id) ON CONFLICT(id) DO NOTHING",
        {"id": _ROW_ID},
    )


def get_config() -> dict[str, Any] | None:
    """Return the single external-git-source config row, or None if unset/un-migrated."""
    try:
        row = (
            _database()
            .execute(
                f"SELECT {_ALL_COLUMNS} FROM skill_git_source WHERE id = :id",
                {"id": _ROW_ID},
            )
            .fetchone()
        )
    except sqlite3.OperationalError as exc:
        # table absent (e.g. an un-migrated env) -> GitOps is simply not configured
        logger.debug("skill_git_source unavailable (%s); treating as unconfigured", exc)
        return None
    return dict(row) if row is not None else None


def set_config(**fields: Any) -> None:
    """Upsert the single config row, updating only the supplied columns.

    Args:
        **fields: Subset of the config columns to set.

    Raises:
        ValueError: if any field is not a recognized config column.
    """
    unknown = set(fields) - set(_CONFIG_COLUMNS)
    if unknown:
        raise ValueError(f"unknown config fields: {sorted(unknown)}")
    if not fields:
        return
    set_clause = ", ".join(f"{col} = :{col}" for col in fields)
    with _database().transaction() as conn:
        _ensure_row(conn)
        conn.execute(
            f"UPDATE skill_git_source SET {set_clause} WHERE id = :_row_id",
            {**fields, "_row_id": _ROW_ID},
        )


def record_sync(*, commit: str | None, at: str, error: str | None) -> None:
    """Update only the sync-state columns (config columns untouched)."""
    with _database().transaction() as conn:
        _ensure_row(conn)
        conn.execute(
            """
            UPDATE skill_git_source
            SET last_synced_commit = :commit, last_sync_at = :at, last_sync_error = :error
            WHERE id = :id
            """,
            {"commit": commit, "at": at, "error": error, "id": _ROW_ID},
        )
