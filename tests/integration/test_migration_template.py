"""The shared cached migration helper must match a fresh migrate, copy on reuse, isolate."""

import sqlite3
from pathlib import Path
from unittest import mock

from alembic import command
from alembic.config import Config

from tests.integration import _migration_template as mt

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


def _fresh_migrate(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def _schema(db_path: Path) -> list[tuple[str, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
    finally:
        conn.close()


def test_helper_schema_matches_fresh_migrate(tmp_path):
    helper_db = tmp_path / "helper.db"
    fresh_db = tmp_path / "fresh.db"
    mt.apply_migrations(helper_db)
    _fresh_migrate(fresh_db)
    assert _schema(helper_db) == _schema(fresh_db)


def test_second_call_copies_template_without_rerunning_alembic(tmp_path):
    mt._template_db.cache_clear()
    with mock.patch.object(mt.command, "upgrade", side_effect=command.upgrade) as upgrade_spy:
        mt.apply_migrations(tmp_path / "a.db")
        mt.apply_migrations(tmp_path / "b.db")
    assert upgrade_spy.call_count == 1
    assert (tmp_path / "a.db").exists()
    assert (tmp_path / "b.db").exists()


def test_materialized_databases_are_independent(tmp_path):
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    mt.apply_migrations(db_a)
    mt.apply_migrations(db_b)

    conn = sqlite3.connect(db_a)
    conn.execute("CREATE TABLE _probe (x INTEGER)")
    conn.commit()
    conn.close()

    conn = sqlite3.connect(db_b)
    leaked = conn.execute("SELECT name FROM sqlite_master WHERE name = '_probe'").fetchone()
    conn.close()
    assert leaked is None
