"""Database runtime boundary for store modules."""

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

Params = Mapping[str, object]
Row = dict[str, Any]

_WAL_BUSY_TIMEOUT_MS = 5000


def _connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL journal mode and busy_timeout set."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_WAL_BUSY_TIMEOUT_MS}")
    return conn


@dataclass(frozen=True)
class DbResult:
    rows: list[Row]
    rowcount: int
    lastrowid: int | None

    def fetchone(self) -> Row | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[Row]:
        return list(self.rows)


@dataclass(frozen=True)
class SQLiteConnection:
    conn: sqlite3.Connection

    def execute(self, sql: str, params: Params | None = None) -> DbResult:
        cursor = self.conn.execute(sql, dict(params or {}))
        rows = _rows_from_cursor(cursor)
        return DbResult(rows=rows, rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)


@dataclass(frozen=True)
class SQLiteDatabase:
    path: Path
    dialect: str = "sqlite"

    def execute(self, sql: str, params: Params | None = None) -> DbResult:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _connect(self.path) as conn:
            cursor = conn.execute(sql, dict(params or {}))
            rows = _rows_from_cursor(cursor)
            return DbResult(rows=rows, rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    @contextmanager
    def transaction(self) -> Iterator[SQLiteConnection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = _connect(self.path)
        try:
            yield SQLiteConnection(conn)
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            conn.close()


def create_database(database_url: str) -> SQLiteDatabase:
    """Create a database adapter from a database URL."""
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        raise ValueError(f"database backend is not supported yet: {parsed.scheme}")
    if parsed.netloc not in {"", "localhost"}:
        raise ValueError("sqlite database_url must use a local file path")
    path = _sqlite_path(database_url, parsed.path)
    return SQLiteDatabase(path=path)


def default_database() -> SQLiteDatabase:
    """Return the configured default SQLiteDatabase.

    Backward-compat fallback for call sites that have not yet migrated to
    explicit TenantRouter injection.  Will be removed once all sites pass
    a database explicitly (tracked under roadmap #3b).
    """
    from fleetent.config import Settings  # local import avoids circular at module level

    return create_database(Settings().database_url)


def _rows_from_cursor(cursor: sqlite3.Cursor) -> list[Row]:
    if cursor.description is None:
        return []
    return [dict(row) for row in cursor.fetchall()]


def _sqlite_path(database_url: str, parsed_path: str) -> Path:
    raw_path = unquote(parsed_path)
    if database_url.startswith("sqlite:////"):
        if raw_path.startswith("//"):
            raw_path = raw_path[1:]
        return Path(raw_path)
    if database_url.startswith("sqlite:///"):
        return Path(raw_path.lstrip("/"))
    return Path(raw_path)
