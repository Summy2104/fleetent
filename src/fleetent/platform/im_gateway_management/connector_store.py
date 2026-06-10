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
    owner_id: str,
    platform: str,
    *,
    enabled: bool | None = None,
    allowlist_enforced: bool | None = None,
    config: str | None = None,
    status: str | None = None,
) -> None:
    """Insert a connector row or update the given fields, keyed by (owner_id, platform)."""
    now = _now()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO im_connectors
                   (owner_id, platform, enabled, allowlist_enforced, config, status,
                    created_at, updated_at)
               VALUES (:owner_id, :platform, COALESCE(:enabled, 0),
                       COALESCE(:allowlist_enforced, 0), :config,
                       COALESCE(:status, 'stopped'), :now, :now)
               ON CONFLICT(owner_id, platform) DO UPDATE SET
                   enabled = COALESCE(excluded.enabled, im_connectors.enabled),
                   allowlist_enforced =
                       COALESCE(excluded.allowlist_enforced, im_connectors.allowlist_enforced),
                   config = COALESCE(excluded.config, im_connectors.config),
                   status = COALESCE(excluded.status, im_connectors.status),
                   updated_at = excluded.updated_at""",
            {
                "owner_id": owner_id,
                "platform": platform,
                "enabled": _bool(enabled),
                "allowlist_enforced": _bool(allowlist_enforced),
                "config": config,
                "status": status,
                "now": now,
            },
        )


def report_status(owner_id: str, platform: str, status: str, error: str | None = None) -> None:
    """Update a connector's status (creating the row if absent). Sets last_error if given."""
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status!r}")
    now = _now()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO im_connectors
                   (owner_id, platform, status, last_error, created_at, updated_at)
               VALUES (:owner_id, :platform, :status, :error, :now, :now)
               ON CONFLICT(owner_id, platform) DO UPDATE SET
                   status = excluded.status,
                   last_error = excluded.last_error,
                   updated_at = excluded.updated_at""",
            {
                "owner_id": owner_id,
                "platform": platform,
                "status": status,
                "error": error,
                "now": now,
            },
        )


def heartbeat(owner_id: str, platform: str) -> None:
    """Refresh last_heartbeat_at without changing status."""
    now = _now()
    with _conn() as conn:
        conn.execute(
            """UPDATE im_connectors SET last_heartbeat_at = :now, updated_at = :now
               WHERE owner_id = :owner_id AND platform = :platform""",
            {"now": now, "owner_id": owner_id, "platform": platform},
        )


def set_enabled(owner_id: str, platform: str, enabled: bool) -> None:
    _set_flag(owner_id, platform, "enabled", enabled)


def set_allowlist_enforced(owner_id: str, platform: str, enforced: bool) -> None:
    _set_flag(owner_id, platform, "allowlist_enforced", enforced)


def get_connector(owner_id: str, platform: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            f"SELECT {_COLS} FROM im_connectors"
            " WHERE owner_id = :owner_id AND platform = :platform",
            {"owner_id": owner_id, "platform": platform},
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_connectors(owner_id: str | None = None) -> list[dict[str, Any]]:
    """List connectors for one owner, or all owners (admin scope) when owner_id is None."""
    with _conn() as conn:
        if owner_id is None:
            rows = conn.execute(
                f"SELECT {_COLS} FROM im_connectors ORDER BY owner_id, platform"
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_COLS} FROM im_connectors WHERE owner_id = :owner_id ORDER BY platform",
                {"owner_id": owner_id},
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


_COLS = (
    "id, owner_id, platform, enabled, allowlist_enforced, config, status, "
    "last_heartbeat_at, last_error, created_at, updated_at"
)
_FIELDS = [c.strip() for c in _COLS.split(",")]


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(_FIELDS, row, strict=True))


def _bool(value: bool | None) -> int | None:
    return None if value is None else int(value)


def _set_flag(owner_id: str, platform: str, column: str, value: bool) -> None:
    with _conn() as conn:
        conn.execute(
            f"""UPDATE im_connectors SET {column} = :value, updated_at = :now
                WHERE owner_id = :owner_id AND platform = :platform""",
            {"value": int(value), "now": _now(), "owner_id": owner_id, "platform": platform},
        )
