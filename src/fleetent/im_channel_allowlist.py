"""IM channel/workspace allowlist: stores allowed scopes and enforces them per platform."""

import datetime

from fleetent import im_connector_store
from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)

_COLS = "id, platform, scope_type, scope_id, allowed, note, created_at"
_FIELDS = [c.strip() for c in _COLS.split(",")]


def add_entry(
    platform: str,
    scope_type: str,
    scope_id: str,
    note: str | None = None,
    allowed: bool = True,
) -> None:
    """Add or update (upsert) an allowlist entry keyed by (platform, scope_type, scope_id)."""
    if scope_type not in ("channel", "workspace"):
        raise ValueError(f"scope_type must be 'channel' or 'workspace', got {scope_type!r}")
    _init_db()
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO im_channel_allowlist
                   (platform, scope_type, scope_id, allowed, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(platform, scope_type, scope_id) DO UPDATE SET
                   allowed = excluded.allowed,
                   note = excluded.note""",
            (platform, scope_type, scope_id, int(allowed), note, now),
        )


def remove_entry(entry_id: int) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute("DELETE FROM im_channel_allowlist WHERE id = ?", (entry_id,))


def list_entries(platform: str | None = None) -> list[dict]:
    _init_db()
    with _conn() as conn:
        if platform is None:
            rows = conn.execute(
                f"SELECT {_COLS} FROM im_channel_allowlist ORDER BY platform, scope_id"
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_COLS} FROM im_channel_allowlist WHERE platform = ? ORDER BY scope_id",
                (platform,),
            ).fetchall()
    return [dict(zip(_FIELDS, r, strict=True)) for r in rows]


def is_allowed(platform: str, channel_id: str, workspace_id: str | None = None) -> bool:
    """Return whether a message in this scope may enter the pipeline.

    Per-platform opt-in: if the connector's allowlist_enforced is off (or the connector
    is unknown), allow everything (backward compatible). When enforced, a channel-level
    or covering workspace-level allowed entry is required.
    """
    connector = im_connector_store.get_connector(platform)
    enforced = bool(connector["allowlist_enforced"]) if connector else False
    if not enforced:
        return True
    _init_db()
    with _conn() as conn:
        if _has_allow(conn, platform, "channel", channel_id):
            return True
        if workspace_id and _has_allow(conn, platform, "workspace", workspace_id):
            return True
    return False


def _has_allow(conn, platform: str, scope_type: str, scope_id: str) -> bool:
    row = conn.execute(
        """SELECT 1 FROM im_channel_allowlist
           WHERE platform = ? AND scope_type = ? AND scope_id = ? AND allowed = 1""",
        (platform, scope_type, scope_id),
    ).fetchone()
    return row is not None


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS im_channel_allowlist (
                id         INTEGER PRIMARY KEY,
                platform   TEXT NOT NULL,
                scope_type TEXT NOT NULL,
                scope_id   TEXT NOT NULL,
                allowed    INTEGER NOT NULL DEFAULT 1,
                note       TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(platform, scope_type, scope_id)
            )"""
        )
