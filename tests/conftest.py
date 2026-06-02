"""Shared test fixtures (merged: zhangyang health cache + main schedule-db isolation)."""

from __future__ import annotations

import pytest

import fleetent.provider_health as provider_health
from fleetent import db


@pytest.fixture(autouse=True)
def _reset_provider_health_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a fresh provider health cache.

    The cache is a process-wide circuit breaker; without a reset a switchable
    failure recorded in one test could leave a model in cooldown for the next,
    making order-dependent tests (e.g. the fallback suite) flaky. A generous
    threshold keeps tests that don't exercise the breaker unaffected.
    """
    monkeypatch.setattr(
        provider_health,
        "_cache",
        provider_health.ProviderHealthCache(failure_threshold=1000, cooldown_seconds=60),
    )


@pytest.fixture
def isolated_schedule_db(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    database_url = f"sqlite:///{tmp_path / 'sched.db'}"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", database_url)
    database = db.create_database(database_url)
    database.execute("""
        CREATE TABLE scheduled_tasks (
            id         TEXT PRIMARY KEY,
            name       TEXT NOT NULL,
            cron_expr  TEXT NOT NULL,
            timezone   TEXT NOT NULL DEFAULT 'UTC',
            user_id    TEXT NOT NULL,
            agent_name TEXT,
            message    TEXT NOT NULL,
            enabled    INTEGER NOT NULL DEFAULT 1,
            source     TEXT NOT NULL DEFAULT 'dynamic',
            created_at TEXT NOT NULL
        )
    """)
    return database
