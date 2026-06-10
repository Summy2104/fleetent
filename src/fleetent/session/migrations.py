"""Session metadata migration list for the Y embedded migration engine.

DDL lifted verbatim from session/index.py ensure_schema; schema intentionally
unchanged so existing metadata rows remain valid after the DB is moved to the
per-agent agent_state.db (3b-1).
"""

from __future__ import annotations

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id    TEXT PRIMARY KEY,
            user_id       TEXT,
            created_at    REAL,
            updated_at    REAL,
            message_count INTEGER,
            agent_name    TEXT
        )
        """,
    ),
]
