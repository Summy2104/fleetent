"""Registration ban store: record and query emails barred from re-registration.

Agent-readable (``user_store`` consults ``is_registration_blocked`` at sign-up) and free of
platform coupling. The admin block/unblock cascade lives in
``platform.user_management.block_service`` — it coordinates platform-owned stores (API keys,
IM accounts) and must not be imported by the agent runtime.
"""

import datetime

from fleetent.user_store import (
    _conn,
)


def is_registration_blocked(email: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM blocked_registrations WHERE email = :email",
            {"email": email},
        ).fetchone()
    return row is not None


def ban_registration(email: str, reason: str, batch_id: str | None = None) -> None:
    """Bar an email from re-registration. Called by the platform block cascade."""
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO blocked_registrations (email, reason, batch_id, created_at)
               VALUES (:email, :reason, :batch_id, :created_at)""",
            {
                "email": email,
                "reason": reason,
                "batch_id": batch_id,
                "created_at": now,
            },
        )
