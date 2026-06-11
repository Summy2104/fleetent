"""SQLite-backed store for tenants and teams.

All writes go through named parameters; schema is owned by Alembic (migrations 067-069).
Connections go through db.py boundary (WAL + busy_timeout) via Settings().database_url.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

_TENANT_COLS = "id, name, status, created_at, approver_user_id"
_TEAM_COLS = "id, tenant_id, name, approver_user_id, created_at"


def _db():
    from fleetent.config import Settings
    from fleetent.db import create_database

    return create_database(Settings().database_url)


# ── tenants ───────────────────────────────────────────────────────────────────


def create_tenant(
    id: str | None = None,
    name: str = "",
    status: str = "active",
) -> dict[str, Any]:
    """Create a new tenant.  ``id`` defaults to a new uuid if not supplied."""
    tenant_id = id if id is not None else str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _db().transaction() as conn:
        conn.execute(
            f"INSERT INTO tenants ({_TENANT_COLS}) VALUES"
            " (:id, :name, :status, :created_at, :approver_user_id)",
            {
                "id": tenant_id,
                "name": name,
                "status": status,
                "created_at": now,
                "approver_user_id": None,
            },
        )
    result = get_tenant(tenant_id)
    assert result is not None
    return result


def get_tenant(tenant_id: str) -> dict[str, Any] | None:
    row = (
        _db()
        .execute(f"SELECT {_TENANT_COLS} FROM tenants WHERE id = :id", {"id": tenant_id})
        .fetchone()
    )
    return dict(row) if row else None


def list_tenants() -> list[dict[str, Any]]:
    rows = _db().execute(f"SELECT {_TENANT_COLS} FROM tenants ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def set_tenant_approver(tenant_id: str, approver_user_id: str | None) -> None:
    with _db().transaction() as conn:
        conn.execute(
            "UPDATE tenants SET approver_user_id = :approver WHERE id = :id",
            {"approver": approver_user_id, "id": tenant_id},
        )


# ── teams ─────────────────────────────────────────────────────────────────────


def create_team(
    id: str | None = None,
    tenant_id: str = "default",
    name: str = "",
) -> dict[str, Any]:
    """Create a new team under ``tenant_id``.  ``id`` defaults to a new uuid."""
    team_id = id if id is not None else str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC).isoformat()
    with _db().transaction() as conn:
        conn.execute(
            f"INSERT INTO teams ({_TEAM_COLS}) VALUES"
            " (:id, :tenant_id, :name, :approver_user_id, :created_at)",
            {
                "id": team_id,
                "tenant_id": tenant_id,
                "name": name,
                "approver_user_id": None,
                "created_at": now,
            },
        )
    result = get_team(team_id)
    assert result is not None
    return result


def get_team(team_id: str) -> dict[str, Any] | None:
    row = (
        _db().execute(f"SELECT {_TEAM_COLS} FROM teams WHERE id = :id", {"id": team_id}).fetchone()
    )
    return dict(row) if row else None


def list_teams(tenant_id: str | None = None) -> list[dict[str, Any]]:
    if tenant_id is not None:
        rows = (
            _db()
            .execute(
                f"SELECT {_TEAM_COLS} FROM teams WHERE tenant_id = :tid ORDER BY created_at",
                {"tid": tenant_id},
            )
            .fetchall()
        )
    else:
        rows = _db().execute(f"SELECT {_TEAM_COLS} FROM teams ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def set_team_approver(team_id: str, approver_user_id: str | None) -> None:
    with _db().transaction() as conn:
        conn.execute(
            "UPDATE teams SET approver_user_id = :approver WHERE id = :id",
            {"approver": approver_user_id, "id": team_id},
        )


# ── user ─────────────────────────────────────────────────────────────────────


def set_user_tenant(user_id: str, tenant_id: str) -> None:
    """Assign a user to a tenant.  Raises KeyError if either does not exist."""
    if get_tenant(tenant_id) is None:
        raise KeyError(f"Tenant not found: {tenant_id!r}")
    row = (
        _db()
        .execute(
            "UPDATE users SET tenant_id = :tenant_id WHERE id = :user_id RETURNING id",
            {"tenant_id": tenant_id, "user_id": user_id},
        )
        .fetchone()
    )
    if row is None:
        raise KeyError(f"User not found: {user_id!r}")
