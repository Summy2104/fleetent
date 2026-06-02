"""SQLite-backed registry of IM platform connectors and their connection status."""

import datetime
from typing import Any

from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)

STATUSES = frozenset(
    {"stopped", "connecting", "connected", "disconnected", "error", "unconfigured"}
)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def upsert_connector(
    platform: str,
    *,
    enabled: bool | None = None,
    allowlist_enforced: bool | None = None,
    config: str | None = None,
    status: str | None = None,
) -> None:
    """Insert a connector row or update the given fields, keyed by platform."""
    _init_db()
    now = _now()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO im_connectors
                   (platform, enabled, allowlist_enforced, config, status, created_at, updated_at)
               VALUES (?, COALESCE(?, 0), COALESCE(?, 0), ?, COALESCE(?, 'stopped'), ?, ?)
               ON CONFLICT(platform) DO UPDATE SET
                   enabled = COALESCE(excluded.enabled, im_connectors.enabled),
                   allowlist_enforced =
                       COALESCE(excluded.allowlist_enforced, im_connectors.allowlist_enforced),
                   config = COALESCE(excluded.config, im_connectors.config),
                   status = COALESCE(excluded.status, im_connectors.status),
                   updated_at = excluded.updated_at""",
            (
                platform,
                _bool(enabled),
                _bool(allowlist_enforced),
                config,
                status,
                now,
                now,
            ),
        )


def report_status(platform: str, status: str, error: str | None = None) -> None:
    """Update a connector's status (creating the row if absent). Sets last_error if given."""
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status!r}")
    _init_db()
    now = _now()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO im_connectors (platform, status, last_error, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(platform) DO UPDATE SET
                   status = excluded.status,
                   last_error = excluded.last_error,
                   updated_at = excluded.updated_at""",
            (platform, status, error, now, now),
        )


def heartbeat(platform: str) -> None:
    """Refresh last_heartbeat_at without changing status."""
    _init_db()
    now = _now()
    with _conn() as conn:
        conn.execute(
            "UPDATE im_connectors SET last_heartbeat_at = ?, updated_at = ? WHERE platform = ?",
            (now, now, platform),
        )


def set_enabled(platform: str, enabled: bool) -> None:
    _set_flag(platform, "enabled", enabled)


def set_allowlist_enforced(platform: str, enforced: bool) -> None:
    _set_flag(platform, "allowlist_enforced", enforced)


def get_connector(platform: str) -> dict[str, Any] | None:
    _init_db()
    with _conn() as conn:
        row = conn.execute(
            f"SELECT {_COLS} FROM im_connectors WHERE platform = ?", (platform,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_connectors() -> list[dict[str, Any]]:
    _init_db()
    with _conn() as conn:
        rows = conn.execute(f"SELECT {_COLS} FROM im_connectors ORDER BY platform").fetchall()
    return [_row_to_dict(r) for r in rows]


_COLS = (
    "id, platform, enabled, allowlist_enforced, config, status, "
    "last_heartbeat_at, last_error, created_at, updated_at"
)
_FIELDS = [c.strip() for c in _COLS.split(",")]


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(_FIELDS, row, strict=True))


def _bool(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _set_flag(platform: str, column: str, value: bool) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute(
            f"UPDATE im_connectors SET {column} = ?, updated_at = ? WHERE platform = ?",
            (int(value), _now(), platform),
        )


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS im_connectors (
                id                 INTEGER PRIMARY KEY,
                platform           TEXT UNIQUE NOT NULL,
                enabled            INTEGER NOT NULL DEFAULT 0,
                allowlist_enforced INTEGER NOT NULL DEFAULT 0,
                config             TEXT,
                status             TEXT NOT NULL DEFAULT 'stopped',
                last_heartbeat_at  TEXT,
                last_error         TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            )"""
        )
