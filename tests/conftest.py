from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent import db


def _apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _reset_long_term_ctx_knowledge_provider():
    # long_term_ctx holds the knowledge provider in a module global; tests that
    # set it must not leak it into later tests (ordering-dependent failures).
    yield
    from fleetent.intelligence import long_term_ctx

    long_term_ctx.set_knowledge_provider(None)


@pytest.fixture
def isolated_schedule_db(tmp_path, monkeypatch):
    db_path = tmp_path / "sched.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", database_url)
    _apply_migrations(db_path)
    return db.create_database(database_url)
