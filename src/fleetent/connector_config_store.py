"""Management-face persistence for the OAuth connector config catalog.

db runtime + named params, no ORM. Only the connector *configuration* (endpoints,
scopes, client_id) lives here. Per-user credentials, consent, refresh, and revoke
are owned by the connectors engine domain. ``client_secret`` is never stored here.
"""

import datetime
import json
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings(anthropic_api_key="").database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def add_connector(
    connector_id: str,
    display_name: str,
    oauth_config: dict[str, Any] | None = None,
    protocol: str = "oauth2",
    enabled: bool = True,
) -> None:
    config = dict(oauth_config or {})
    config.pop("client_secret", None)  # never persist the secret
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO connectors
                (id, display_name, protocol, oauth_config, enabled, created_at, updated_at)
            VALUES (:id, :display_name, :protocol, :oauth_config, :enabled,
                    :created_at, :updated_at)
            """,
            {
                "id": connector_id,
                "display_name": display_name,
                "protocol": protocol,
                "oauth_config": json.dumps(config) if config else None,
                "enabled": 1 if enabled else 0,
                "created_at": now,
                "updated_at": now,
            },
        )


_EDITABLE = {"display_name", "oauth_config", "enabled"}


def edit_connector(connector_id: str, **fields: Any) -> None:
    updates = {k: v for k, v in fields.items() if k in _EDITABLE and v is not None}
    if "oauth_config" in updates:
        cfg = dict(updates["oauth_config"])
        cfg.pop("client_secret", None)
        updates["oauth_config"] = json.dumps(cfg)
    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0
    if not updates:
        return
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{k} = :{k}" for k in updates)
    with _database().transaction() as conn:
        conn.execute(
            f"UPDATE connectors SET {assignments} WHERE id = :id",
            {**updates, "id": connector_id},
        )


def get_connector(connector_id: str) -> dict[str, Any] | None:
    row = (
        _database()
        .execute(
            "SELECT id, display_name, protocol, oauth_config, enabled, created_at, updated_at "
            "FROM connectors WHERE id = :id",
            {"id": connector_id},
        )
        .fetchone()
    )
    return _decode(row) if row else None


def list_connectors() -> list[dict[str, Any]]:
    rows = (
        _database()
        .execute(
            "SELECT id, display_name, protocol, oauth_config, enabled, created_at, updated_at "
            "FROM connectors ORDER BY id"
        )
        .fetchall()
    )
    return [_decode(r) for r in rows]


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["oauth_config"] = json.loads(out["oauth_config"]) if out.get("oauth_config") else {}
    return out
