"""Embedded forward-only migration engine (Y) for agent-side SQLite libraries.

Each agent-side library supplies its own MIGRATIONS list; this module provides
the shared engine that applies them using PRAGMA user_version as the version stamp.

Usage::

    MIGRATIONS: list[tuple[int, str]] = [
        (1, "CREATE TABLE ..."),
        (2, "ALTER TABLE ..."),
    ]

    migrate(db, MIGRATIONS)   # called at open-time; idempotent when already current
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from fleetent.db import SQLiteDatabase

logger = logging.getLogger(__name__)


class SchemaTooNewError(RuntimeError):
    """DB version stamp is higher than the code knows about — refuse to open."""


class MigrationError(RuntimeError):
    """A migration step failed; the DB version was not advanced."""


def migrate(db: SQLiteDatabase, migrations: list[tuple[int, str]]) -> None:
    """Apply any pending migrations from *migrations* to *db*.

    Args:
        db: The target SQLite database.
        migrations: Ordered list of ``(version, sql)`` pairs.  Versions must
            start at 1 and be contiguous; ``sql`` is executed as a single
            statement inside its own transaction.

    Raises:
        SchemaTooNewError: The DB's ``user_version`` is greater than the
            highest version in *migrations* (code is older than the DB).
        MigrationError: A migration SQL statement failed; the version stamp
            was not advanced for that step.
    """
    if not migrations:
        return

    current_code_version = migrations[-1][0]
    current_db_version = _read_user_version(db.path)

    if current_db_version > current_code_version:
        raise SchemaTooNewError(
            f"DB at {db.path} has schema version {current_db_version} "
            f"but code only knows up to version {current_code_version}. "
            "Refusing to open — this binary is too old."
        )

    for version, sql in migrations:
        if version <= current_db_version:
            continue
        _apply_step(db.path, version, sql.strip())


def _read_user_version(db_path: Path) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _apply_step(db_path: Path, version: int, sql: str) -> None:
    """Execute *sql* and bump user_version atomically inside one transaction.

    SQLite PRAGMA user_version changes are transactional; DDL (CREATE TABLE /
    ALTER TABLE) is also transactional in SQLite.  Using isolation_level=None
    gives manual BEGIN/COMMIT/ROLLBACK control so both changes land together.
    """
    conn = sqlite3.connect(db_path)
    conn.isolation_level = None  # manual transaction control
    try:
        conn.execute("BEGIN")
        try:
            for statement in _split_sql_statements(sql):
                _execute_idempotent(conn, statement, version)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.execute("COMMIT")
        except Exception as exc:
            conn.execute("ROLLBACK")
            raise MigrationError(f"Migration step v{version} failed: {exc}") from exc
    finally:
        conn.close()


def _execute_idempotent(conn: sqlite3.Connection, statement: str, version: int) -> None:
    """Execute one migration statement, tolerating a benign already-applied ADD COLUMN.

    ``CREATE TABLE IF NOT EXISTS`` already lets a table another authority created (Alembic,
    in mixed-schema test DBs / the dual-authority ``mcp_user_tokens``) be a no-op. SQLite has
    no ``ADD COLUMN IF NOT EXISTS``, so an ``ALTER TABLE ... ADD COLUMN`` whose column is
    already present raises ``duplicate column name``; treat that as already-applied (skip,
    keep the transaction, advance the version). Every other failure propagates.
    """
    try:
        conn.execute(statement)
    except sqlite3.OperationalError as exc:
        if _is_benign_duplicate_column(statement, exc):
            logger.info("migration_add_column_already_present v=%d stmt=%r", version, statement)
            return
        raise


def _is_benign_duplicate_column(statement: str, exc: sqlite3.OperationalError) -> bool:
    """Whether *exc* is a 'duplicate column name' for an ``ADD COLUMN`` (already applied)."""
    lowered = statement.lower()
    return "duplicate column name" in str(exc).lower() and "add column" in lowered


def _split_sql_statements(sql: str) -> list[str]:
    """Split a migration script into executable SQLite statements.

    Migration steps are usually one statement, but some forward-only schema
    changes need a tightly ordered script while still sharing one version stamp.
    """
    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        buffer.append(line)
        candidate = "\n".join(buffer).strip()
        if sqlite3.complete_statement(candidate):
            finalized = candidate.rstrip(";").strip()
            if finalized:
                statements.append(finalized)
            buffer.clear()
    remainder = "\n".join(buffer).strip()
    if remainder:
        statements.append(remainder.rstrip(";").strip())
    return statements
