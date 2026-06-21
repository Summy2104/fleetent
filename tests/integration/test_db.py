import sqlite3
import threading
from pathlib import Path

import pytest

from fleetent import db
from fleetent.schema_migrations import migrate


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path}"


def test_create_database_from_sqlite_url(tmp_path):
    db_path = tmp_path / "fleetent.db"
    database = db.create_database(_sqlite_url(db_path))

    assert database.dialect == "sqlite"
    assert database.path == db_path


def test_create_database_from_relative_sqlite_url():
    database = db.create_database("sqlite:///data/fleetent.db")

    assert database.path == Path("data/fleetent.db")


def test_create_database_rejects_unsupported_backend():
    with pytest.raises(ValueError, match="not supported"):
        db.create_database("postgresql://fleetent:secret@localhost/fleetent")


def test_create_substrate_preserves_sqlite_migrations_and_pragmas(tmp_path: Path) -> None:
    db_path = tmp_path / "substrate.db"
    backend = db.create_substrate(_sqlite_url(db_path))

    migrate(
        backend,
        [
            (
                1,
                """
                CREATE TABLE IF NOT EXISTS widgets (
                    id TEXT PRIMARY KEY
                )
                """,
            )
        ],
    )

    assert sqlite3.connect(db_path).execute("PRAGMA user_version").fetchone() == (1,)
    assert backend.execute("PRAGMA journal_mode").fetchone() == {"journal_mode": "wal"}
    assert backend.execute("PRAGMA busy_timeout").fetchone() == {"timeout": 5000}


def test_execute_supports_named_parameters_and_fetchone(tmp_path):
    database = db.create_database(_sqlite_url(tmp_path / "fleetent.db"))
    database.execute("CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
    database.execute(
        "INSERT INTO items (id, name) VALUES (:id, :name)",
        {"id": "item-1", "name": "Alpha"},
    )

    result = database.execute("SELECT id, name FROM items WHERE id = :id", {"id": "item-1"})

    assert result.fetchone() == {"id": "item-1", "name": "Alpha"}


def test_execute_fetchall_and_rowcount(tmp_path):
    database = db.create_database(_sqlite_url(tmp_path / "fleetent.db"))
    database.execute("CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
    database.execute(
        "INSERT INTO items (id, name) VALUES (:id, :name)",
        {"id": "item-1", "name": "Alpha"},
    )
    database.execute(
        "INSERT INTO items (id, name) VALUES (:id, :name)",
        {"id": "item-2", "name": "Beta"},
    )

    rows = database.execute("SELECT id, name FROM items ORDER BY id").fetchall()
    update_result = database.execute(
        "UPDATE items SET name = :name WHERE id = :id",
        {"id": "item-2", "name": "Bravo"},
    )

    assert rows == [
        {"id": "item-1", "name": "Alpha"},
        {"id": "item-2", "name": "Beta"},
    ]
    assert update_result.rowcount == 1


def test_transaction_commits_on_success(tmp_path):
    database = db.create_database(_sqlite_url(tmp_path / "fleetent.db"))
    database.execute("CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT NOT NULL)")

    with database.transaction() as conn:
        conn.execute(
            "INSERT INTO items (id, name) VALUES (:id, :name)",
            {"id": "item-1", "name": "Alpha"},
        )

    assert database.execute("SELECT id FROM items").fetchall() == [{"id": "item-1"}]


def test_transaction_rolls_back_on_error(tmp_path):
    database = db.create_database(_sqlite_url(tmp_path / "fleetent.db"))
    database.execute("CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT NOT NULL)")

    with pytest.raises(RuntimeError, match="boom"), database.transaction() as conn:
        conn.execute(
            "INSERT INTO items (id, name) VALUES (:id, :name)",
            {"id": "item-1", "name": "Alpha"},
        )
        raise RuntimeError("boom")

    assert database.execute("SELECT id FROM items").fetchall() == []


# --- WAL + busy_timeout PRAGMA verification (task 1.1) ---


def test_sqlite_database_enables_wal_journal_mode(tmp_path: Path) -> None:
    database = db.create_database(_sqlite_url(tmp_path / "wal.db"))
    database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    result = database.execute("PRAGMA journal_mode")

    assert result.fetchone() == {"journal_mode": "wal"}


def test_sqlite_database_sets_nonzero_busy_timeout(tmp_path: Path) -> None:
    database = db.create_database(_sqlite_url(tmp_path / "wal.db"))
    database.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    result = database.execute("PRAGMA busy_timeout")

    row = result.fetchone()
    assert row is not None
    assert row["timeout"] > 0


# --- Concurrent behaviour (task 1.2) ---


def test_concurrent_reader_not_blocked_by_open_write_transaction(tmp_path: Path) -> None:
    """WAL: an in-progress write transaction does not block a concurrent reader."""
    db_path = tmp_path / "concurrent.db"
    writer_db = db.create_database(_sqlite_url(db_path))
    writer_db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, v TEXT)")
    writer_db.execute("INSERT INTO items VALUES (1, 'initial')")

    write_started = threading.Event()
    write_finish = threading.Event()
    reader_row: list[dict] = []
    writer_errors: list[Exception] = []

    def long_writer() -> None:
        try:
            with writer_db.transaction() as conn:
                conn.execute("INSERT INTO items VALUES (2, 'pending')")
                write_started.set()
                write_finish.wait(timeout=3.0)
        except Exception as exc:
            writer_errors.append(exc)

    t = threading.Thread(target=long_writer)
    t.start()
    write_started.wait(timeout=3.0)

    reader_db = db.create_database(_sqlite_url(db_path))
    row = reader_db.execute("SELECT v FROM items WHERE id = 1").fetchone()
    reader_row.append(row or {})

    write_finish.set()
    t.join(timeout=5.0)

    assert not writer_errors, f"Writer raised: {writer_errors}"
    assert reader_row[0].get("v") == "initial"


def test_busy_timeout_allows_second_writer_after_exclusive_lock_released(
    tmp_path: Path,
) -> None:
    """busy_timeout: second writer waits while a raw EXCLUSIVE lock is held, then succeeds."""
    db_path = tmp_path / "concurrent.db"
    setup_db = db.create_database(_sqlite_url(db_path))
    setup_db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, v TEXT)")

    exclusive_held = threading.Event()
    release_exclusive = threading.Event()
    holder_errors: list[Exception] = []

    def exclusive_holder() -> None:
        # timeout=0 so the holder itself fails fast if something goes wrong
        conn = sqlite3.connect(str(db_path), timeout=0)
        try:
            conn.isolation_level = None
            conn.execute("BEGIN EXCLUSIVE")
            conn.execute("INSERT INTO items VALUES (1, 'first')")
            exclusive_held.set()
            release_exclusive.wait(timeout=3.0)
            conn.execute("COMMIT")
        except Exception as exc:
            holder_errors.append(exc)
        finally:
            conn.close()

    t = threading.Thread(target=exclusive_holder)
    t.start()
    exclusive_held.wait(timeout=3.0)

    # Release the lock after 100 ms — the second writer must wait for it
    threading.Timer(0.1, release_exclusive.set).start()

    second_db = db.create_database(_sqlite_url(db_path))
    second_db.execute("INSERT INTO items VALUES (2, 'second')")

    t.join(timeout=5.0)
    assert not holder_errors, f"Exclusive holder raised: {holder_errors}"

    rows = setup_db.execute("SELECT id FROM items ORDER BY id").fetchall()
    assert rows == [{"id": 1}, {"id": 2}]
