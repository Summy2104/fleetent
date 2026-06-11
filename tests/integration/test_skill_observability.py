"""Integration tests for skill hit tracking + observability (skill-observability-tracking)."""

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.observability.traces import TraceEvent, record_trace_event
from fleetent.platform.skill_management import skill_admin_store
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    db = SQLiteDatabase(path=db_path)
    migrate(db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr("fleetent.observability.traces._state_db", db)
    return db_path


def _emit_hit(skill: str, session: str | None, agent: str = "agent-a") -> None:
    record_trace_event(
        TraceEvent(
            run_id=session or "",
            event_type="skill_hit",
            payload={"skill_name": skill},
            session_id=session,
            agent_id=agent,
        )
    )


def test_skill_hit_traces_then_observe_returns_real_counts(db):
    _emit_hit("crm-ops", "sess-1", "agent-a")
    _emit_hit("crm-ops", "sess-1", "agent-a")  # same session
    _emit_hit("crm-ops", "sess-2", "agent-b")
    _emit_hit("other", "sess-3", "agent-a")

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


def test_observe_tolerates_null_session(db):
    # CLI runs have no session id; the hit is counted but excluded from sessions.
    _emit_hit("cli-skill", None)
    obs = skill_admin_store.observe("cli-skill")
    assert obs["hits"] == 1
    assert obs["sessions"] == []
