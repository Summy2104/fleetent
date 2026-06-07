"""Registration ban store: record and query emails barred from re-registration.

Agent-readable (``user_store`` consults ``is_registration_blocked`` at sign-up) and free of
platform coupling. The admin block/unblock cascade lives in
``platform.user_management.block_service`` — it coordinates platform-owned stores (API keys,
IM accounts) and must not be imported by the agent runtime.
"""

import datetime

from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)


def is_registration_blocked(email: str) -> bool:
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM blocked_registrations WHERE email = ?", (email,)
        ).fetchone()
    return row is not None


def ban_registration(email: str, reason: str, batch_id: str | None = None) -> None:
    """Bar an email from re-registration. Called by the platform block cascade."""
    _init_db()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO blocked_registrations (email, reason, batch_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (email, reason, batch_id, now),
        )


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS blocked_registrations (
                email      TEXT PRIMARY KEY,
                reason     TEXT,
                batch_id   TEXT,
                created_at TEXT NOT NULL
            )"""
        )
