"""Migration contract: askit task-queue tables must not exist in head schema.

Corresponds to spec scenario: 'schema 中不存在 askit 任务队列表'.
"""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")

_ASKIT_TABLES = {"askit_tasks", "askit_task_logs", "askit_workspaces"}


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()


def _run_alembic(db_path: Path, target: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    if target == "head" or target.startswith("+") or target.startswith("-"):
        command.upgrade(cfg, target) if not target.startswith("-") else command.downgrade(cfg, target)
    else:
        command.upgrade(cfg, target)


def _upgrade(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def _downgrade(db_path: Path, target: str) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.downgrade(cfg, target)


def test_head_schema_does_not_contain_askit_tables(tmp_path):
    """After upgrade head, askit task-queue tables MUST NOT exist."""
    db = tmp_path / "test.db"
    _upgrade(db)
    tables = _tables(db)
    assert not (_ASKIT_TABLES & tables), (
        f"askit tables still present in head schema: {_ASKIT_TABLES & tables}"
    )


def test_roundtrip_upgrade_downgrade_upgrade(tmp_path):
    """upgrade head → downgrade -1 → upgrade head must complete without error."""
    db = tmp_path / "roundtrip.db"
    _upgrade(db)
    _downgrade(db, "-1")
    _upgrade(db)
    tables = _tables(db)
    assert not (_ASKIT_TABLES & tables), (
        f"askit tables present after roundtrip: {_ASKIT_TABLES & tables}"
    )


def test_downgrade_restores_askit_tables(tmp_path):
    """Downgrading below the drop migration (064) MUST reconstruct the askit tables."""
    db = tmp_path / "downgrade.db"
    _upgrade(db)
    _downgrade(db, "063")
    tables = _tables(db)
    assert _ASKIT_TABLES <= tables, (
        f"downgrade did not restore askit tables; missing: {_ASKIT_TABLES - tables}"
    )
