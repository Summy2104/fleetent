import pytest

from fleetent import db


@pytest.fixture
def isolated_schedule_db(tmp_path, monkeypatch):
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
