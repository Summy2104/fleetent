from pathlib import Path

import pytest

from fleetent import db


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
