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
    agent_id: int | None = None,
) -> None:
    config = dict(oauth_config or {})
    config.pop("client_secret", None)  # never persist the secret
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO connectors
                (agent_id, id, display_name, protocol, oauth_config, enabled,
                 created_at, updated_at)
            VALUES (:agent_id, :id, :display_name, :protocol, :oauth_config, :enabled,
                    :created_at, :updated_at)
            """,
            {
                "agent_id": agent_id,
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


_COLS = "agent_id, id, display_name, protocol, oauth_config, enabled, created_at, updated_at"


def edit_connector(connector_id: str, agent_id: int | None = None, **fields: Any) -> None:
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
    scope = "agent_id = :agent_id" if agent_id is not None else "agent_id IS NULL"
    with _database().transaction() as conn:
        conn.execute(
            f"UPDATE connectors SET {assignments} WHERE id = :id AND {scope}",
            {**updates, "id": connector_id, "agent_id": agent_id},
        )


def get_connector(connector_id: str, agent_id: int | None = None) -> dict[str, Any] | None:
    # Resolution: an agent-owned row wins; otherwise fall back to the global default.
    if agent_id is not None:
        row = (
            _database()
            .execute(
                f"SELECT {_COLS} FROM connectors WHERE id = :id AND agent_id = :agent_id",
                {"id": connector_id, "agent_id": agent_id},
            )
            .fetchone()
        )
        if row:
            return _decode(row)
    row = (
        _database()
        .execute(
            f"SELECT {_COLS} FROM connectors WHERE id = :id AND agent_id IS NULL",
            {"id": connector_id},
        )
        .fetchone()
    )
    return _decode(row) if row else None


def list_connectors(agent_id: int | None = None) -> list[dict[str, Any]]:
    db = _database()
    globals_ = {
        r["id"]: _decode(r)
        for r in db.execute(
            f"SELECT {_COLS} FROM connectors WHERE agent_id IS NULL ORDER BY id"
        ).fetchall()
    }
    if agent_id is None:
        return list(globals_.values())
    # Overlay agent-owned rows on top of the global defaults.
    for r in db.execute(
        f"SELECT {_COLS} FROM connectors WHERE agent_id = :agent_id ORDER BY id",
        {"agent_id": agent_id},
    ).fetchall():
        decoded = _decode(r)
        globals_[decoded["id"]] = decoded
    return sorted(globals_.values(), key=lambda c: c["id"])


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["oauth_config"] = json.loads(out["oauth_config"]) if out.get("oauth_config") else {}
    return out
