"""Management-face persistence for the external services registry."""

from __future__ import annotations

import datetime
import json
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def add_service(
    service_id: str,
    display_name: str,
    oauth_config: dict[str, Any] | None = None,
    protocol: str = "oauth2",
    enabled: bool = True,
) -> None:
    config = dict(oauth_config or {})
    config.pop("client_secret", None)
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO external_services
                (service_id, display_name, protocol, oauth_config, enabled, created_at, updated_at)
            VALUES
                (
                    :service_id,
                    :display_name,
                    :protocol,
                    :oauth_config,
                    :enabled,
                    :created_at,
                    :updated_at
                )
            """,
            {
                "service_id": service_id,
                "display_name": display_name,
                "protocol": protocol,
                "oauth_config": json.dumps(config) if config else None,
                "enabled": 1 if enabled else 0,
                "created_at": now,
                "updated_at": now,
            },
        )


_EDITABLE = {"display_name", "oauth_config", "protocol", "enabled"}
_COLS = "service_id, display_name, protocol, oauth_config, enabled, created_at, updated_at"


def edit_service(service_id: str, **fields: Any) -> None:
    updates = {k: v for k, v in fields.items() if k in _EDITABLE and v is not None}
    if "oauth_config" in updates:
        config = dict(updates["oauth_config"])
        config.pop("client_secret", None)
        updates["oauth_config"] = json.dumps(config)
    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0
    if not updates:
        return
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{key} = :{key}" for key in updates)
    with _database().transaction() as conn:
        conn.execute(
            f"UPDATE external_services SET {assignments} WHERE service_id = :service_id",
            {**updates, "service_id": service_id},
        )


def delete_service(service_id: str) -> None:
    with _database().transaction() as conn:
        conn.execute(
            "DELETE FROM external_services WHERE service_id = :service_id",
            {"service_id": service_id},
        )


def get_service(service_id: str) -> dict[str, Any] | None:
    row = (
        _database()
        .execute(
            f"SELECT {_COLS} FROM external_services WHERE service_id = :service_id",
            {"service_id": service_id},
        )
        .fetchone()
    )
    return _decode(row) if row else None


def list_services() -> list[dict[str, Any]]:
    rows = (
        _database().execute(f"SELECT {_COLS} FROM external_services ORDER BY service_id").fetchall()
    )
    return [_decode(row) for row in rows]


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["oauth_config"] = json.loads(out["oauth_config"]) if out.get("oauth_config") else {}
    return out
