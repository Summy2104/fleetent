"""Read-only helpers for materialized default-agent state."""

from __future__ import annotations

import sqlite3

from fleetent.config import Settings
from fleetent.db import create_database


def is_default(agent_id: int) -> bool:
    """Whether the management control plane marks this agent as default.

    Legacy/lightweight DBs may not have the ``agent_admin_state`` table yet; default to
    false so export/materialize stays usable in unit tests and pre-migration contexts.
    """
    try:
        row = (
            create_database(Settings().database_url)
            .execute(
                "SELECT is_default FROM agent_admin_state WHERE agent_id = :agent_id",
                {"agent_id": agent_id},
            )
            .fetchone()
        )
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        return False
    return bool(row["is_default"]) if row is not None else False
