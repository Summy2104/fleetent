"""Per-user and global usage quotas (token + call-count) with limit checks."""

from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)


def set_quota(scope: str, token_limit: int | None = None, call_limit: int | None = None) -> None:
    """Set limits for a scope (``global`` or ``user:{id}``). None means unlimited."""
    _init_db()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO quotas (scope, token_limit, call_limit)
               VALUES (?, ?, ?)
               ON CONFLICT(scope) DO UPDATE SET
                   token_limit = excluded.token_limit,
                   call_limit = excluded.call_limit""",
            (scope, token_limit, call_limit),
        )


def record_usage(user_id: str, tokens: int) -> None:
    """Add consumption to the user's and the global counters."""
    _init_db()
    for scope in (f"user:{user_id}", "global"):
        with _conn() as conn:
            conn.execute(
                """INSERT INTO quota_usage (scope, tokens_used, calls_used)
                   VALUES (?, ?, 1)
                   ON CONFLICT(scope) DO UPDATE SET
                       tokens_used = tokens_used + excluded.tokens_used,
                       calls_used = calls_used + 1""",
                (scope, tokens),
            )


def check_quota(user_id: str, tokens: int = 0) -> bool:
    """Return False if adding `tokens`/one call would exceed any applicable limit."""
    _init_db()
    for scope in (f"user:{user_id}", "global"):
        limits = _get_quota(scope)
        if limits is None:
            continue
        token_limit, call_limit = limits
        used_tokens, used_calls = _get_usage(scope)
        if token_limit is not None and used_tokens + tokens > token_limit:
            return False
        if call_limit is not None and used_calls + 1 > call_limit:
            return False
    return True


def _get_quota(scope: str) -> tuple[int | None, int | None] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT token_limit, call_limit FROM quotas WHERE scope = ?", (scope,)
        ).fetchone()
    return (row[0], row[1]) if row else None


def _get_usage(scope: str) -> tuple[int, int]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT tokens_used, calls_used FROM quota_usage WHERE scope = ?", (scope,)
        ).fetchone()
    return (row[0], row[1]) if row else (0, 0)


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS quotas (
                scope       TEXT PRIMARY KEY,
                token_limit INTEGER,
                call_limit  INTEGER
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS quota_usage (
                scope       TEXT PRIMARY KEY,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                calls_used  INTEGER NOT NULL DEFAULT 0
            )"""
        )
