"""Database runtime boundary for store modules."""

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import unquote

from fleetent.substrate.backend import BaseSubstrateBackend, SubstrateCapabilities

Params = Mapping[str, object]
Row = dict[str, Any]

_WAL_BUSY_TIMEOUT_MS = 5000


def _connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL journal mode and busy_timeout set."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_WAL_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _connect_ro(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection in read-only mode (mode=ro URI flag).

    Does NOT set journal_mode or busy_timeout — those are write-side concerns.
    Raises sqlite3.OperationalError if the file does not exist (mode=ro requires an
    existing file; it never creates one).
    """
    uri = path.as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
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
class SQLiteSubstrateBackend(BaseSubstrateBackend):
    path: Path
    dialect: ClassVar[str] = "sqlite"
    capabilities: ClassVar[SubstrateCapabilities] = SubstrateCapabilities(
        network=False,
        shared_across_hosts=False,
        embedded_migrations=True,
    )

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

    def local_path(self) -> str | None:
        return str(self.path)


SQLiteDatabase = SQLiteSubstrateBackend


@dataclass(frozen=True)
class ReadOnlySQLiteDatabase:
    """Read-only view of a SQLite database.

    Opens with SQLite ``mode=ro`` — writes are rejected at the driver level.
    Does NOT run any migrations on open; schema version is left entirely untouched.
    Intended for platform-side projection of agent databases: the platform reads
    without ever migrating or writing agent-side state.

    Raises ``sqlite3.OperationalError`` if the underlying file does not exist
    (mode=ro never creates files).
    """

    path: Path
    dialect: str = "sqlite"

    def execute(self, sql: str, params: Params | None = None) -> DbResult:
        with _connect_ro(self.path) as conn:
            cursor = conn.execute(sql, dict(params or {}))
            rows = _rows_from_cursor(cursor)
            return DbResult(rows=rows, rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    @contextmanager
    def transaction(self) -> Iterator[SQLiteConnection]:
        conn = _connect_ro(self.path)
        try:
            yield SQLiteConnection(conn)
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            conn.close()


def create_substrate(database_url: str) -> BaseSubstrateBackend:
    """Create a substrate backend from a database URL or local path."""
    from fleetent.substrate.factory import create_substrate as _create_substrate

    return _create_substrate(database_url)


def create_database(database_url: str) -> SQLiteDatabase:
    """Create a database adapter from a database URL."""
    substrate = create_substrate(database_url)
    if not isinstance(substrate, SQLiteSubstrateBackend):
        raise ValueError(f"database backend is not supported yet: {substrate.dialect}")
    return substrate


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
