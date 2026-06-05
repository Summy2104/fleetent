"""DB-managed knowledge-base source connectors (Google Drive / Confluence).

The admin console writes connector definitions here (db runtime, named params, no
ORM). ``config`` holds the kind-specific fields + credential *env-reference names*
(never raw secrets). A builder turns the stored rows into a ``KnowledgeBaseSettings``
so the existing config-driven ingestion engine (intelligence.knowledge_base.operations)
can run check/status/sync against them unchanged.
"""

import datetime
import json
from typing import Any

from fleetent.config import (
    ConfluenceConnectorSettings,
    ConfluenceConnectorsSettings,
    GoogleDriveConnectorSettings,
    GoogleDriveConnectorsSettings,
    KnowledgeBaseSettings,
    Settings,
)
from fleetent.db import SQLiteDatabase, create_database

KINDS = ("google_drive", "confluence")

# Kind-specific config keys persisted in the JSON blob (env-ref names, not secrets).
_GOOGLE_DRIVE_KEYS = (
    "folder_id",
    "recursive",
    "credential_ref",
    "access_token_env",
    "refresh_token_env",
    "client_id_env",
    "client_secret_env",
    "token_uri_env",
)
_CONFLUENCE_KEYS = (
    "base_url",
    "username",
    "username_env",
    "credential_ref",
    "api_token_env",
    "scope_type",
    "space_key",
    "page_id",
    "include_children",
)


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


_COLS = "connector_id, kind, enabled, tenant_id, kb_id, config, created_at, updated_at"


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["enabled"] = bool(out["enabled"])
    out["config"] = json.loads(out["config"]) if out.get("config") else {}
    return out


def list_connectors() -> list[dict[str, Any]]:
    rows = (
        _database().execute(f"SELECT {_COLS} FROM kb_connectors ORDER BY connector_id").fetchall()
    )
    return [_decode(r) for r in rows]


def get_connector(connector_id: str) -> dict[str, Any] | None:
    row = (
        _database()
        .execute(
            f"SELECT {_COLS} FROM kb_connectors WHERE connector_id = :id",
            {"id": connector_id},
        )
        .fetchone()
    )
    return _decode(row) if row else None


def add_connector(
    connector_id: str,
    kind: str,
    tenant_id: str,
    kb_id: str,
    config: dict[str, Any],
    enabled: bool = True,
) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown connector kind: {kind}")
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            f"INSERT INTO kb_connectors ({_COLS}) VALUES "
            "(:connector_id, :kind, :enabled, :tenant_id, :kb_id, :config, :created_at,"
            " :updated_at)",
            {
                "connector_id": connector_id,
                "kind": kind,
                "enabled": 1 if enabled else 0,
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "config": json.dumps(_clean_config(kind, config)),
                "created_at": now,
                "updated_at": now,
            },
        )


_EDITABLE = {"enabled", "tenant_id", "kb_id", "config"}


def edit_connector(connector_id: str, **fields: Any) -> None:
    row = get_connector(connector_id)
    if row is None:
        raise ValueError(f"connector not found: {connector_id}")
    updates = {k: v for k, v in fields.items() if k in _EDITABLE and v is not None}
    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0
    if "config" in updates:
        updates["config"] = json.dumps(_clean_config(row["kind"], updates["config"]))
    if not updates:
        return
    updates["updated_at"] = _now()
    assignments = ", ".join(f"{k} = :{k}" for k in updates)
    with _database().transaction() as conn:
        conn.execute(
            f"UPDATE kb_connectors SET {assignments} WHERE connector_id = :id",
            {**updates, "id": connector_id},
        )


def delete_connector(connector_id: str) -> bool:
    with _database().transaction() as conn:
        cur = conn.execute(
            "DELETE FROM kb_connectors WHERE connector_id = :id", {"id": connector_id}
        )
        return bool(cur.rowcount)


def _clean_config(kind: str, config: dict[str, Any]) -> dict[str, Any]:
    keys = _GOOGLE_DRIVE_KEYS if kind == "google_drive" else _CONFLUENCE_KEYS
    return {k: v for k, v in (config or {}).items() if k in keys and v is not None}


def as_knowledge_base_settings() -> KnowledgeBaseSettings:
    """Assemble the stored connectors into a KnowledgeBaseSettings the ingestion
    engine understands, so operations.* can run against DB-managed connectors."""
    gdrive: list[GoogleDriveConnectorSettings] = []
    confluence: list[ConfluenceConnectorSettings] = []
    for row in list_connectors():
        base = {
            "connector_id": row["connector_id"],
            "tenant_id": row["tenant_id"],
            "kb_id": row["kb_id"],
            "enabled": row["enabled"],
            **row["config"],
        }
        if row["kind"] == "google_drive":
            gdrive.append(GoogleDriveConnectorSettings(**base))
        else:
            confluence.append(ConfluenceConnectorSettings(**base))
    return KnowledgeBaseSettings(
        google_drive=GoogleDriveConnectorsSettings(connectors=gdrive),
        confluence=ConfluenceConnectorsSettings(connectors=confluence),
    )
