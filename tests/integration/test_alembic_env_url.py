"""Integration tests for migrations/env.py DATABASE_URL injection.

Verifies that setting DATABASE_URL in the environment causes alembic upgrade head
to write tables into that database, and that without DATABASE_URL the alembic.ini
default is used.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


def _make_config(ini_db: Path) -> Config:
    """Create an alembic Config using real migrations with a custom ini-level default URL."""
    cfg = Config()
    cfg.set_main_option("script_location", _MIGRATIONS_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{ini_db}")
    return cfg


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return tables


def test_database_url_env_redirects_migration_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When DATABASE_URL is set, alembic upgrade writes to that database, not the ini default."""
    target_db = tmp_path / "target.db"
    ini_fallback_db = tmp_path / "ini_fallback.db"

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{target_db}")

    cfg = _make_config(ini_fallback_db)
    command.upgrade(cfg, "head")

    # DATABASE_URL should have been used → target_db has tables
    assert target_db.exists(), "target_db should have been created via DATABASE_URL"
    assert "traces" in _table_names(target_db)

    # ini fallback should NOT have been touched
    assert not ini_fallback_db.exists(), "ini fallback db should be untouched when DATABASE_URL is set"


def test_migration_uses_ini_default_when_database_url_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When DATABASE_URL is not set, alembic upgrade uses the ini-level sqlalchemy.url default."""
    ini_db = tmp_path / "ini_default.db"

    monkeypatch.delenv("DATABASE_URL", raising=False)

    cfg = _make_config(ini_db)
    command.upgrade(cfg, "head")

    assert ini_db.exists()
    assert "traces" in _table_names(ini_db)
