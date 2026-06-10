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

import sqlite3
from pathlib import Path

from fleetent.db import SQLiteDatabase


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
    """Execute *sql* inside a transaction; bump user_version on success."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN")
        try:
            conn.executescript(sql)
            # PRAGMA user_version cannot run inside BEGIN…COMMIT, so we commit
            # the DDL first, then set the version in a separate connection step.
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise MigrationError(
                f"Migration step v{version} failed: {exc}"
            ) from exc
        # Bump version after the DDL has been safely committed.
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
    finally:
        conn.close()
