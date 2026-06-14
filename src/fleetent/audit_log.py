"""Append-only audit log for platform management actions, searchable by filters."""

import datetime
import json
from typing import Any

from fleetent.user_store import (
    DB_PATH as DB_PATH,  # noqa: F401 — re-export for test monkeypatching
)
from fleetent.user_store import (
    _conn,
)

_COLS = "id, actor_user_id, action, target_type, target_id, detail, batch_id, created_at"
_FIELDS = [c.strip() for c in _COLS.split(",")]


def write_audit(
    actor_user_id: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
    batch_id: str | None = None,
) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT INTO audit_log
                   (actor_user_id, action, target_type, target_id, detail, batch_id, created_at)
               VALUES (:actor_user_id, :action, :target_type, :target_id, :detail, :batch_id,
                       :created_at)""",
            {
                "actor_user_id": actor_user_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "detail": json.dumps(detail) if detail is not None else None,
                "batch_id": batch_id,
                "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
            },
        )


def search_audit(
    actor: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, str] = {}
    for column, value in (
        ("actor_user_id", actor),
        ("action", action),
        ("target_type", target_type),
        ("target_id", target_id),
    ):
        if value is not None:
            clauses.append(f"{column} = :{column}")
            params[column] = value
    if since is not None:
        clauses.append("created_at >= :since")
        params["since"] = since
    if until is not None:
        clauses.append("created_at <= :until")
        params["until"] = until
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT {_COLS} FROM audit_log{where} ORDER BY created_at, id", params
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    d = dict(zip(_FIELDS, row, strict=True))
    d["detail"] = json.loads(d["detail"]) if d["detail"] else None
    return d
