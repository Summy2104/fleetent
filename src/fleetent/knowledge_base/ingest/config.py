from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from fleetent.config import (
    ConfluenceConnectorSettings,
    ConfluenceConnectorsSettings,
    GoogleDriveConnectorSettings,
    GoogleDriveConnectorsSettings,
    KnowledgeBaseSettings,
)


def as_knowledge_base_settings(
    connectors: Iterable[Mapping[str, Any]] | None = None,
    *,
    default_tenant_id: str = "default",
    default_kb_id: str = "global",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> KnowledgeBaseSettings:
    """Build ingest settings from connector rows provided by control-plane caller."""
    rows = list(connectors or [])
    gdrive_connectors: list[GoogleDriveConnectorSettings] = []
    confluence_connectors: list[ConfluenceConnectorSettings] = []
    for row in rows:
        kind = row.get("kind")
        if kind not in {"google_drive", "confluence"}:
            continue
        config = row.get("config") if isinstance(row.get("config"), dict) else {}
        if not isinstance(config, dict):
            raise TypeError("connector row config must be a mapping")
        connector_id = _as_str(row["connector_id"])
        tenant_id = _as_str(row.get("tenant_id", default_tenant_id))
        kb_id = _as_str(row.get("kb_id", default_kb_id))
        enabled = bool(row.get("enabled", True))
        if kind == "google_drive":
            gdrive_connectors.append(
                GoogleDriveConnectorSettings(
                    connector_id=connector_id,
                    tenant_id=tenant_id,
                    kb_id=kb_id,
                    enabled=enabled,
                    folder_id=_as_str(config.get("folder_id")),
                    recursive=bool(config.get("recursive", True)),
                    credential_ref=_as_str(config.get("credential_ref")),
                    access_token_env=_as_str(config.get("access_token_env")),
                    refresh_token_env=_as_str(config.get("refresh_token_env")),
                    client_id_env=_as_str(config.get("client_id_env")),
                    client_secret_env=_as_str(config.get("client_secret_env")),
                    token_uri_env=_as_str(config.get("token_uri_env")),
                )
            )
        else:
            confluence_connectors.append(
                ConfluenceConnectorSettings(
                    connector_id=connector_id,
                    tenant_id=tenant_id,
                    kb_id=kb_id,
                    enabled=enabled,
                    base_url=_as_str(config.get("base_url")),
                    username=_as_str(config.get("username")),
                    username_env=_as_str(config.get("username_env")),
                    credential_ref=_as_str(config.get("credential_ref")),
                    api_token_env=_as_str(config.get("api_token_env")),
                    scope_type=_as_scope_type(config.get("scope_type")),
                    space_key=_as_optional_str(config.get("space_key")),
                    page_id=_as_optional_str(config.get("page_id")),
                    include_children=bool(config.get("include_children", False)),
                )
            )

    return KnowledgeBaseSettings(
        default_tenant_id=default_tenant_id,
        default_kb_id=default_kb_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        google_drive=GoogleDriveConnectorsSettings(connectors=gdrive_connectors),
        confluence=ConfluenceConnectorsSettings(connectors=confluence_connectors),
    )


def _as_str(value: object) -> str:
    return str(value) if value is not None else ""


def _as_scope_type(value: object) -> Literal["space", "page"] | None:
    if value in {"space", "page"}:
        return value  # type: ignore[return-value]
    return None


def _as_optional_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None
