"""Integration tests for the externalize-monitoring Alembic migration.

Verifies that upgrade head drops the four monitoring tables, and that the
downgrade/upgrade round-trip leaves the schema clean.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")
_MONITORING_TABLES = {"alert_rules", "alerts", "metric_samples", "maintenance_windows"}


def _make_cfg(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _table_names(db_path: Path) -> set[str]:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def test_head_schema_has_no_monitoring_tables(tmp_path: Path) -> None:
    """After upgrade head the four monitoring tables must not exist."""
    db = tmp_path / "test.db"
    command.upgrade(_make_cfg(db), "head")
    tables = _table_names(db)
    for table in _MONITORING_TABLES:
        assert table not in tables, f"Expected {table!r} to be absent after upgrade head"


def test_monitoring_migration_round_trip(tmp_path: Path) -> None:
    """upgrade head → downgrade below the drop (063) → upgrade head must succeed cleanly."""
    db = tmp_path / "rt.db"
    cfg = _make_cfg(db)

    command.upgrade(cfg, "head")
    assert not _MONITORING_TABLES & _table_names(db), (
        "monitoring tables present after first upgrade"
    )

    command.downgrade(cfg, "062")
    # Below the drop migration the monitoring tables are present again (recreated)
    tables_after_down = _table_names(db)
    for table in _MONITORING_TABLES:
        assert table in tables_after_down, f"Expected {table!r} after downgrade to 062"

    command.upgrade(cfg, "head")
    tables_after_reup = _table_names(db)
    for table in _MONITORING_TABLES:
        assert table not in tables_after_reup, f"Expected {table!r} absent after second upgrade"
