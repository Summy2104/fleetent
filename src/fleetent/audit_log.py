"""Append-only audit log for platform management actions, searchable by filters."""

import datetime
import json

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
    detail: dict | None = None,
    batch_id: str | None = None,
) -> None:
    _init_db()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO audit_log
                   (actor_user_id, action, target_type, target_id, detail, batch_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                actor_user_id,
                action,
                target_type,
                target_id,
                json.dumps(detail) if detail is not None else None,
                batch_id,
                datetime.datetime.now(datetime.UTC).isoformat(),
            ),
        )


def search_audit(
    actor: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    _init_db()
    clauses: list[str] = []
    params: list[str] = []
    for column, value in (
        ("actor_user_id", actor),
        ("action", action),
        ("target_type", target_type),
        ("target_id", target_id),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("created_at <= ?")
        params.append(until)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT {_COLS} FROM audit_log{where} ORDER BY created_at, id", params
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: tuple) -> dict:
    d = dict(zip(_FIELDS, row, strict=True))
    d["detail"] = json.loads(d["detail"]) if d["detail"] else None
    return d


def _init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                id            INTEGER PRIMARY KEY,
                actor_user_id TEXT,
                action        TEXT NOT NULL,
                target_type   TEXT,
                target_id     TEXT,
                detail        TEXT,
                batch_id      TEXT,
                created_at    TEXT NOT NULL
            )"""
        )
