"""Integration tests for skill hit tracking + observability (skill-observability-tracking)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent.platform.skill_management import skill_admin_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_record_hit_then_observe_returns_real_counts(db):
    skill_admin_store.record_hit("crm-ops", "agent-a", "sess-1")
    skill_admin_store.record_hit("crm-ops", "agent-a", "sess-1")  # same session
    skill_admin_store.record_hit("crm-ops", "agent-b", "sess-2")
    skill_admin_store.record_hit("other", "agent-a", "sess-3")

    obs = skill_admin_store.observe("crm-ops")
    assert obs["skill_name"] == "crm-ops"
    assert obs["hits"] == 3
    assert set(obs["sessions"]) == {"sess-1", "sess-2"}  # deduped
    assert obs["stale"] is False


def test_observe_unhit_skill_is_zero_not_stale(db):
    obs = skill_admin_store.observe("never-used")
    assert obs["hits"] == 0
    assert obs["sessions"] == []
    assert obs["stale"] is False


def test_record_hit_tolerates_null_session(db):
    # CLI runs have no session id; the row is still recorded but excluded from sessions.
    skill_admin_store.record_hit("cli-skill", None, None)
    obs = skill_admin_store.observe("cli-skill")
    assert obs["hits"] == 1
    assert obs["sessions"] == []
