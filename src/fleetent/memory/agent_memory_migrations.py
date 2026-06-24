"""Embedded forward-only migrations for per-agent agent_memory.db (Y-managed).

This list is the sole DDL authority for agent_memory.db.
Never append entries here to agent_state_migrations.py — that list is per-agent
state; agent_memory.db is per-agent memory with its own independent user_version stamp.
Isolation is provided by the per-agent physical file — no scope columns needed.
"""

from __future__ import annotations

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
CREATE TABLE agent_memory_items (
    id          TEXT NOT NULL PRIMARY KEY,
    type        TEXT NOT NULL,
    content     TEXT NOT NULL,
    status      TEXT NOT NULL,
    source      TEXT NOT NULL,
    source_ref  TEXT,
    created_by  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)
""",
    ),
    (
        2,
        "CREATE INDEX idx_agent_memory_status ON agent_memory_items (status)",
    ),
    (
        3,
        "CREATE INDEX idx_agent_memory_source_ref ON agent_memory_items (source, source_ref)",
    ),
]
