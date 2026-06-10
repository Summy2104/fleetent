"""IM channel/workspace allowlist: stores allowed scopes and enforces them per platform."""

import datetime
from typing import Any

from fleetent.platform.im_gateway_management import connector_store
from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)

_COLS = "id, owner_id, platform, scope_type, scope_id, allowed, note, created_at"
_FIELDS = [c.strip() for c in _COLS.split(",")]


def add_entry(
    owner_id: str,
    platform: str,
    scope_type: str,
    scope_id: str,
    note: str | None = None,
    allowed: bool = True,
) -> None:
    """Add or update (upsert) an entry keyed by (owner_id, platform, scope_type, scope_id)."""
    if scope_type not in ("channel", "workspace"):
        raise ValueError(f"scope_type must be 'channel' or 'workspace', got {scope_type!r}")
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO im_channel_allowlist
                   (owner_id, platform, scope_type, scope_id, allowed, note, created_at)
               VALUES (:owner_id, :platform, :scope_type, :scope_id, :allowed, :note, :now)
               ON CONFLICT(owner_id, platform, scope_type, scope_id) DO UPDATE SET
                   allowed = excluded.allowed,
                   note = excluded.note""",
            {
                "owner_id": owner_id,
                "platform": platform,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "allowed": int(allowed),
                "note": note,
                "now": now,
            },
        )


def remove_entry(entry_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM im_channel_allowlist WHERE id = :id", {"id": entry_id})


def list_entries(owner_id: str | None = None, platform: str | None = None) -> list[dict[str, Any]]:
    """List allowlist entries. owner_id=None lists across all owners (admin scope)."""
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if owner_id is not None:
        clauses.append("owner_id = :owner_id")
        params["owner_id"] = owner_id
    if platform is not None:
        clauses.append("platform = :platform")
        params["platform"] = platform
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _conn() as conn:
        order = " ORDER BY owner_id, platform, scope_id"
        rows = conn.execute(
            f"SELECT {_COLS} FROM im_channel_allowlist{where}{order}",
            params,
        ).fetchall()
    return [dict(zip(_FIELDS, r, strict=True)) for r in rows]


def is_allowed(
    owner_id: str, platform: str, channel_id: str, workspace_id: str | None = None
) -> bool:
    """Return whether a message in this scope may enter the pipeline.

    Per-owner-platform opt-in: if the connector's allowlist_enforced is off (or the connector
    is unknown), allow everything (backward compatible). When enforced, a channel-level
    or covering workspace-level allowed entry is required.
    """
    connector = connector_store.get_connector(owner_id, platform)
    enforced = bool(connector["allowlist_enforced"]) if connector else False
    if not enforced:
        return True
    with _conn() as conn:
        if _has_allow(conn, owner_id, platform, "channel", channel_id):
            return True
        if workspace_id and _has_allow(conn, owner_id, platform, "workspace", workspace_id):
            return True
    return False


def _has_allow(conn: Any, owner_id: str, platform: str, scope_type: str, scope_id: str) -> bool:
    row = conn.execute(
        """SELECT 1 FROM im_channel_allowlist
           WHERE owner_id = :owner_id AND platform = :platform
             AND scope_type = :scope_type AND scope_id = :scope_id AND allowed = 1""",
        {
            "owner_id": owner_id,
            "platform": platform,
            "scope_type": scope_type,
            "scope_id": scope_id,
        },
    ).fetchone()
    return row is not None
