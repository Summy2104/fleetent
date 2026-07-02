from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fleetent.config import KnowledgeBaseSettings
from fleetent.db import SQLiteDatabase
from fleetent.knowledge_base.config import (
    KnowledgeConfigSnapshot,
    KnowledgeSourceConfig,
)
from fleetent.knowledge_base.connectors.confluence import (
    ConfluenceAuthError,
    ConfluenceClient,
    ConfluenceConnectorConfig,
    HttpConfluenceClient,
    plan_confluence_sync,
    sync_confluence,
)
from fleetent.knowledge_base.connectors.google_drive import (
    GoogleDriveAuthError,
    GoogleDriveClient,
    GoogleDriveConnectorConfig,
    HttpGoogleDriveClient,
    plan_google_drive_sync,
    sync_google_drive,
)
from fleetent.structured_logging import _redact_value

ConnectorType = Literal["google_drive", "confluence"]
ConnectorSettings = KnowledgeConfigSnapshot | KnowledgeBaseSettings | object
_SECRET_WORD_RE = re.compile(
    r"\b(token|secret|password|api[_-]?key|authorization|credential)[\s:=_-]+([^\s,;]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ConnectorSummary:
    connector_id: str
    connector_type: ConnectorType
    enabled: bool
    tenant_id: str
    kb_id: str
    scope: str
    credential_ref_summary: str


@dataclass(frozen=True)
class ConnectorDefinition:
    connector_id: str
    connector_type: ConnectorType
    enabled: bool
    config: GoogleDriveConnectorConfig | ConfluenceConnectorConfig


@dataclass(frozen=True)
class ConnectorCheckResult:
    connector_id: str
    status: str
    message: str


@dataclass(frozen=True)
class ConnectorSyncResult:
    connector_id: str
    status: str
    summary: dict[str, int]
    error: str | None = None


@dataclass(frozen=True)
class ConnectorStatus:
    connector_id: str
    connector_type: str
    tenant_id: str
    kb_id: str
    last_status: str
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_summary: dict[str, object]
    last_error: str | None


@dataclass(frozen=True)
class SmokeStepStatus:
    status: Literal["passed", "failed", "skipped"]
    skipped_reason: str | None = None


@dataclass(frozen=True)
class RealConnectorSmokeStatus:
    connector_id: str
    check: SmokeStepStatus
    dry_run: SmokeStepStatus
    execute_sync: SmokeStepStatus


def list_configured_connectors(
    settings: ConnectorSettings | None = None,
) -> list[ConnectorSummary]:
    """List configured knowledge-base connectors without exposing credential payloads."""
    return [_summary_for_definition(item) for item in _connector_definitions(_kb_config(settings))]


def get_connector_config(
    connector_id: str,
    *,
    settings: ConnectorSettings | None = None,
) -> ConnectorDefinition:
    """Return one configured connector definition."""
    for definition in _connector_definitions(_kb_config(settings)):
        if definition.connector_id == connector_id:
            return definition
    raise ValueError(f"unknown connector_id: {connector_id}")


def _get_connector_definition(
    connector_id: str,
    settings: ConnectorSettings | None,
) -> ConnectorDefinition:
    try:
        return get_connector_config(connector_id, settings=settings)
    except TypeError:
        # Backward compatibility for monkeypatched callables that still expose
        # a legacy signature without keyword-only settings.
        return get_connector_config(connector_id)


async def check_connector(
    connector_id: str,
    *,
    settings: ConnectorSettings | None = None,
    google_drive_client: GoogleDriveClient | None = None,
    confluence_client: ConfluenceClient | None = None,
    env: Mapping[str, str] | None = None,
) -> ConnectorCheckResult:
    """Check connector credential reference and remote scope accessibility."""
    definition = _get_connector_definition(connector_id, settings)
    if not definition.enabled:
        return ConnectorCheckResult(connector_id, "disabled", "connector is disabled")
    credential_result = _check_credential(definition)
    if credential_result is not None:
        return ConnectorCheckResult(connector_id, *credential_result)
    try:
        if definition.connector_type == "google_drive":
            google_config = _google_config(definition)
            google_client = google_drive_client or _build_google_drive_client(
                google_config, env=env
            )
            google_client.list_files(google_config.folder_id, recursive=google_config.recursive)
        else:
            confluence_config = _confluence_config(definition)
            confluence_client_value = confluence_client or _build_confluence_client(
                confluence_config, env=env
            )
            await plan_confluence_sync(
                confluence_config,
                client=confluence_client_value,
                sleep=_no_sleep,
            )
    except (GoogleDriveAuthError, ConfluenceAuthError) as exc:
        return ConnectorCheckResult(connector_id, "auth_failed", _sanitize_text(str(exc)))
    except Exception as exc:
        return ConnectorCheckResult(connector_id, "scope_unreachable", _sanitize_text(str(exc)))
    return ConnectorCheckResult(connector_id, "ok", "connector is reachable")


async def run_connector_sync(
    connector_id: str,
    *,
    settings: ConnectorSettings | None = None,
    dry_run: bool = False,
    google_drive_client: GoogleDriveClient | None = None,
    confluence_client: ConfluenceClient | None = None,
    env: Mapping[str, str] | None = None,
) -> ConnectorSyncResult:
    """Run connector dry-run or manual sync and persist latest status."""
    definition = _get_connector_definition(connector_id, settings)
    started_at = _now()
    if not definition.enabled:
        result = ConnectorSyncResult(connector_id, "disabled", {})
        _record_definition_status(definition, result, started_at=started_at)
        return result
    try:
        result = await _run_enabled_connector_sync(
            definition,
            dry_run=dry_run,
            google_drive_client=google_drive_client,
            confluence_client=confluence_client,
            env=env,
        )
    except (GoogleDriveAuthError, ConfluenceAuthError) as exc:
        result = ConnectorSyncResult(connector_id, "auth_failed", {}, _sanitize_text(str(exc)))
    except Exception as exc:
        status = "dry_run_failed" if dry_run else "sync_failed"
        result = ConnectorSyncResult(connector_id, status, {}, _sanitize_text(str(exc)))
    _record_definition_status(definition, result, started_at=started_at)
    return result


def get_connector_status(
    connector_id: str,
    *,
    settings: ConnectorSettings | None = None,
    database: SQLiteDatabase | None = None,
) -> ConnectorStatus:
    """Read the latest known connector operation status."""
    definition = _get_connector_definition(connector_id, settings)
    db = _database(database)
    row = db.execute(
        """
        SELECT
            connector_id, connector_type, tenant_id, kb_id, last_status,
            last_started_at, last_finished_at, last_summary_json, last_error
        FROM knowledge_connector_status
        WHERE connector_id = :connector_id
        """,
        {"connector_id": connector_id},
    ).fetchone()
    if row is None:
        return ConnectorStatus(
            connector_id=definition.connector_id,
            connector_type=definition.connector_type,
            tenant_id=definition.config.tenant_id,
            kb_id=definition.config.kb_id,
            last_status="never_run",
            last_started_at=None,
            last_finished_at=None,
            last_summary={},
            last_error=None,
        )
    return _row_to_status(row)


def list_connector_statuses(
    tenant_id: str,
    *,
    kb_id: str | None = None,
    limit: int = 20,
    database: SQLiteDatabase | None = None,
) -> list[ConnectorStatus]:
    """List latest connector statuses for one tenant, newest first."""
    rows = (
        _database(database)
        .execute(
            """
        SELECT
            connector_id, connector_type, tenant_id, kb_id, last_status,
            last_started_at, last_finished_at, last_summary_json, last_error
        FROM knowledge_connector_status
        WHERE tenant_id = :tenant_id
          AND (:kb_id IS NULL OR kb_id = :kb_id)
        ORDER BY updated_at DESC, connector_id ASC
        LIMIT :limit
        """,
            {"tenant_id": tenant_id, "kb_id": kb_id, "limit": limit},
        )
        .fetchall()
    )
    return [_row_to_status(row) for row in rows]


def record_connector_status(
    *,
    connector_id: str,
    connector_type: str,
    tenant_id: str,
    kb_id: str,
    status: str,
    summary: dict[str, object],
    error: str | None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    database: SQLiteDatabase | None = None,
) -> None:
    """Persist the latest connector status summary."""
    started = started_at or _now()
    finished = finished_at or _now()
    _database(database).execute(
        """
        INSERT INTO knowledge_connector_status (
            connector_id, connector_type, tenant_id, kb_id, last_status,
            last_started_at, last_finished_at, last_summary_json, last_error, updated_at
        )
        VALUES (
            :connector_id, :connector_type, :tenant_id, :kb_id, :last_status,
            :last_started_at, :last_finished_at, :last_summary_json, :last_error, :updated_at
        )
        ON CONFLICT(connector_id) DO UPDATE SET
            connector_type = excluded.connector_type,
            tenant_id = excluded.tenant_id,
            kb_id = excluded.kb_id,
            last_status = excluded.last_status,
            last_started_at = excluded.last_started_at,
            last_finished_at = excluded.last_finished_at,
            last_summary_json = excluded.last_summary_json,
            last_error = excluded.last_error,
            updated_at = excluded.updated_at
        """,
        {
            "connector_id": connector_id,
            "connector_type": connector_type,
            "tenant_id": tenant_id,
            "kb_id": kb_id,
            "last_status": status,
            "last_started_at": started.isoformat(),
            "last_finished_at": finished.isoformat(),
            "last_summary_json": json.dumps(
                _redact_value(summary),
                ensure_ascii=False,
                sort_keys=True,
            ),
            "last_error": _sanitize_text(error) if error else None,
            "updated_at": finished.isoformat(),
        },
    )
    _database(database).execute(
        """
        INSERT INTO knowledge_connector_sync_history
            (id, connector_id, tenant_id, kb_id, status,
             summary_json, error, started_at, finished_at)
        VALUES
            (:id, :connector_id, :tenant_id, :kb_id, :status,
             :summary_json, :error, :started_at, :finished_at)
        """,
        {
            "id": uuid.uuid4().hex,
            "connector_id": connector_id,
            "tenant_id": tenant_id,
            "kb_id": kb_id,
            "status": status,
            "summary_json": json.dumps(
                _redact_value(summary),
                ensure_ascii=False,
                sort_keys=True,
            ),
            "error": _sanitize_text(error) if error else None,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
        },
    )


def list_connector_sync_history(
    connector_id: str,
    limit: int = 20,
    *,
    database: SQLiteDatabase | None = None,
) -> list[dict[str, Any]]:
    """Return the most recent sync history rows for a connector, newest first."""
    rows = (
        _database(database)
        .execute(
            """
        SELECT id, connector_id, tenant_id, kb_id, status, summary_json, error,
               started_at, finished_at
        FROM knowledge_connector_sync_history
        WHERE connector_id = :connector_id
        ORDER BY finished_at DESC
        LIMIT :limit
        """,
            {"connector_id": connector_id, "limit": limit},
        )
        .fetchall()
    )
    return [
        {
            "id": r["id"],
            "connector_id": r["connector_id"],
            "tenant_id": r["tenant_id"],
            "kb_id": r["kb_id"],
            "status": r["status"],
            "summary": json.loads(r["summary_json"]) if r.get("summary_json") else {},
            "error": r["error"],
            "started_at": r["started_at"],
            "finished_at": r["finished_at"],
        }
        for r in rows
    ]


def real_connector_smoke_gate(
    *,
    connector_id: str,
    smoke_enabled: bool,
    credential_ref: str | None,
    execute_sync: bool,
    execute_enabled: bool,
    pilot_fixture: bool,
) -> RealConnectorSmokeStatus:
    """Return explicit opt-in gate status for real connector smoke operations."""
    if not smoke_enabled:
        skipped = SmokeStepStatus("skipped", "real smoke opt-in flag is absent")
        return RealConnectorSmokeStatus(connector_id, skipped, skipped, skipped)
    if not credential_ref:
        skipped = SmokeStepStatus("skipped", "credential_ref is absent")
        return RealConnectorSmokeStatus(connector_id, skipped, skipped, skipped)
    check = SmokeStepStatus("passed")
    dry_run = SmokeStepStatus("passed")
    if not execute_sync:
        execute = SmokeStepStatus("skipped", "execute sync was not requested")
    elif not execute_enabled:
        execute = SmokeStepStatus("skipped", "execute opt-in flag is absent")
    elif not pilot_fixture:
        execute = SmokeStepStatus("skipped", "source is not marked as a Pilot fixture")
    else:
        execute = SmokeStepStatus("passed")
    return RealConnectorSmokeStatus(connector_id, check, dry_run, execute)


async def _run_enabled_connector_sync(
    definition: ConnectorDefinition,
    *,
    dry_run: bool,
    google_drive_client: GoogleDriveClient | None,
    confluence_client: ConfluenceClient | None,
    env: Mapping[str, str] | None,
) -> ConnectorSyncResult:
    if definition.connector_type == "google_drive":
        google_config = _google_config(definition)
        google_client = google_drive_client or _build_google_drive_client(google_config, env=env)
        if dry_run:
            google_plan = await plan_google_drive_sync(google_config, client=google_client)
            return ConnectorSyncResult(
                definition.connector_id, "dry_run_ok", _summary_dict(google_plan.summary)
            )
        google_summary = await sync_google_drive(google_config, client=google_client)
        return ConnectorSyncResult(
            definition.connector_id, "sync_succeeded", _summary_dict(google_summary)
        )

    confluence_config = _confluence_config(definition)
    confluence_client_value = confluence_client or _build_confluence_client(
        confluence_config, env=env
    )
    if dry_run:
        confluence_plan = await plan_confluence_sync(
            confluence_config,
            client=confluence_client_value,
            sleep=_no_sleep,
        )
        return ConnectorSyncResult(
            definition.connector_id, "dry_run_ok", _summary_dict(confluence_plan.summary)
        )
    confluence_summary = await sync_confluence(
        confluence_config,
        client=confluence_client_value,
    )
    return ConnectorSyncResult(
        definition.connector_id,
        "sync_succeeded",
        _summary_dict(confluence_summary),
    )


def _create_google_drive_client(
    config: GoogleDriveConnectorConfig, *, env: Mapping[str, str] | None = None
) -> GoogleDriveClient:
    return HttpGoogleDriveClient(
        credential_ref=config.credential_ref,
        access_token_env=config.access_token_env,
        refresh_token_env=config.refresh_token_env,
        client_id_env=config.client_id_env,
        client_secret_env=config.client_secret_env,
        token_uri_env=config.token_uri_env,
        env=env,
    )


def _create_confluence_client(
    base_url: str,
    username: str,
    api_token_env: str,
    *,
    env: Mapping[str, str] | None = None,
) -> ConfluenceClient:
    return HttpConfluenceClient(
        base_url=base_url,
        username=username,
        credential_ref=f"env:{api_token_env}" if api_token_env else "",
        env=env,
    )


def _build_google_drive_client(
    config: GoogleDriveConnectorConfig, *, env: Mapping[str, str] | None = None
) -> GoogleDriveClient:
    if env is None:
        return _create_google_drive_client(config)
    return _create_google_drive_client(config, env=env)


def _build_confluence_client(
    config: ConfluenceConnectorConfig, *, env: Mapping[str, str] | None = None
) -> ConfluenceClient:
    username = _resolve_env_value(
        config.username,
        config.username_env,
        field_name="username",
        env=env,
    )
    if env is None:
        return _create_confluence_client(config.base_url, username, config.api_token_env)
    return _create_confluence_client(
        config.base_url,
        username,
        config.api_token_env,
        env=env,
    )


def _connector_definitions(config: KnowledgeConfigSnapshot) -> list[ConnectorDefinition]:
    definitions = [
        _source_definition(source) for kb in config.knowledge_bases for source in kb.sources
    ]
    seen: set[str] = set()
    for definition in definitions:
        if definition.connector_id in seen:
            raise ValueError(f"duplicate connector_id: {definition.connector_id}")
        seen.add(definition.connector_id)
    return definitions


def _source_definition(source: KnowledgeSourceConfig) -> ConnectorDefinition:
    if source.type == "google_drive":
        return _google_definition(source)
    return _confluence_definition(source)


def _google_definition(item: KnowledgeSourceConfig) -> ConnectorDefinition:
    return ConnectorDefinition(
        connector_id=item.id,
        connector_type="google_drive",
        enabled=item.enabled,
        config=GoogleDriveConnectorConfig(
            connector_id=item.id,
            tenant_id=item.tenant_id,
            kb_id=item.kb_id,
            folder_id=item.folder_id,
            credential_ref=item.credential_ref,
            recursive=item.recursive,
            access_token_env=item.access_token_env,
            refresh_token_env=item.refresh_token_env,
            client_id_env=item.client_id_env,
            client_secret_env=item.client_secret_env,
            token_uri_env=item.token_uri_env,
        ),
    )


def _confluence_definition(item: KnowledgeSourceConfig) -> ConnectorDefinition:
    return ConnectorDefinition(
        connector_id=item.id,
        connector_type="confluence",
        enabled=item.enabled,
        config=ConfluenceConnectorConfig(
            connector_id=item.id,
            tenant_id=item.tenant_id,
            kb_id=item.kb_id,
            base_url=item.base_url,
            username=item.username,
            credential_ref=_resolve_confluence_credential_ref(item),
            scope_type=item.scope_type or ("page" if item.page_id else "space"),
            username_env=item.username_env,
            api_token_env=_resolve_confluence_api_token_env(item),
            space_key=item.space_key,
            page_id=item.page_id,
            include_children=item.include_children,
        ),
    )


def _resolve_confluence_credential_ref(item: KnowledgeSourceConfig) -> str:
    if item.api_token_env:
        return f"env:{item.api_token_env}"
    return item.credential_ref


def _resolve_confluence_api_token_env(item: KnowledgeSourceConfig) -> str:
    if item.api_token_env:
        return item.api_token_env
    if item.credential_ref.startswith("env:"):
        return item.credential_ref.removeprefix("env:")
    return ""


def _summary_for_definition(definition: ConnectorDefinition) -> ConnectorSummary:
    if definition.connector_type == "google_drive":
        google_config = _google_config(definition)
        scope = f"folder:{google_config.folder_id}"
    else:
        confluence_config = _confluence_config(definition)
        scope = (
            f"page:{confluence_config.page_id}"
            if confluence_config.scope_type == "page"
            else f"space:{confluence_config.space_key}"
        )
    return ConnectorSummary(
        connector_id=definition.connector_id,
        connector_type=definition.connector_type,
        enabled=definition.enabled,
        tenant_id=definition.config.tenant_id,
        kb_id=definition.config.kb_id,
        scope=scope,
        credential_ref_summary=_connector_credential_summary(definition),
    )


def _check_credential(definition: ConnectorDefinition) -> tuple[str, str] | None:
    try:
        if definition.connector_type == "google_drive":
            payload = _read_google_drive_credential(_google_config(definition))
        else:
            payload = _read_credential_ref(definition.config.credential_ref)
    except FileNotFoundError:
        return ("credential_missing", "credential reference is missing")
    except KeyError:
        return ("credential_missing", "credential environment variable is missing")
    except Exception:
        return ("credential_invalid", "credential reference is invalid")
    if not payload.strip():
        return ("credential_invalid", "credential payload is empty")
    if definition.connector_type == "google_drive":
        try:
            json.loads(payload)
        except json.JSONDecodeError:
            return ("credential_invalid", "Google Drive credential payload is invalid")
    return None


def _connector_credential_summary(definition: ConnectorDefinition) -> str:
    if definition.connector_type == "google_drive":
        config = _google_config(definition)
        if config.access_token_env:
            return "env:FLEETENT_GOOGLE_DRIVE_*"
    return _credential_ref_summary(definition.config.credential_ref)


def _read_google_drive_credential(
    config: GoogleDriveConnectorConfig, *, env: Mapping[str, str] | None = None
) -> str:
    if config.credential_ref:
        return _read_credential_ref(config.credential_ref, env=env)
    mapping = {
        "access_token": _env_get(config.access_token_env, env=env)
        if config.access_token_env
        else "",
        "refresh_token": _env_get(config.refresh_token_env, env=env)
        if config.refresh_token_env
        else "",
        "client_id": _env_get(config.client_id_env, env=env) if config.client_id_env else "",
        "client_secret": _env_get(config.client_secret_env, env=env)
        if config.client_secret_env
        else "",
        "token_uri": _env_get(config.token_uri_env, env=env) if config.token_uri_env else "",
    }
    if not any(mapping.values()):
        raise KeyError("google drive env credentials")
    return json.dumps(
        {key: value for key, value in mapping.items() if value},
        ensure_ascii=False,
        sort_keys=True,
    )


def _read_credential_ref(credential_ref: str, *, env: Mapping[str, str] | None = None) -> str:
    source_env = env if env is not None else os.environ
    if credential_ref.startswith("env:"):
        env_name = credential_ref.removeprefix("env:")
        if env_name in source_env:
            return source_env[env_name]
        if _has_google_drive_flat_env(env_name, env=source_env):
            return _google_drive_flat_env_payload(env_name, env=source_env)
        if env_name not in source_env:
            raise KeyError(env_name)
    path = Path(credential_ref.removeprefix("file://")).expanduser()
    return path.read_text(encoding="utf-8")


def _resolve_env_value(
    value: str,
    env_name: str,
    *,
    field_name: str,
    env: Mapping[str, str] | None = None,
) -> str:
    if value:
        return value
    if not env_name:
        return ""
    resolved = _env_get(env_name, env=env)
    if resolved:
        return resolved
    raise ValueError(f"{field_name} env var is missing: {env_name}")


def _has_google_drive_flat_env(prefix: str, *, env: Mapping[str, str] | None = None) -> bool:
    return any(
        _env_get(f"{prefix}_{suffix}", env=env)
        for suffix in (
            "ACCESS_TOKEN",
            "REFRESH_TOKEN",
            "CLIENT_ID",
            "CLIENT_SECRET",
            "TOKEN_URI",
        )
    )


def _google_drive_flat_env_payload(prefix: str, *, env: Mapping[str, str] | None = None) -> str:
    mapping = {
        "access_token": _env_get(f"{prefix}_ACCESS_TOKEN", default="", env=env),
        "refresh_token": _env_get(f"{prefix}_REFRESH_TOKEN", default="", env=env),
        "client_id": _env_get(f"{prefix}_CLIENT_ID", default="", env=env),
        "client_secret": _env_get(f"{prefix}_CLIENT_SECRET", default="", env=env),
        "token_uri": _env_get(
            f"{prefix}_TOKEN_URI",
            default="https://oauth2.googleapis.com/token",
            env=env,
        ),
    }
    return json.dumps(
        {key: value for key, value in mapping.items() if value},
        ensure_ascii=False,
        sort_keys=True,
    )


def _env_get(
    env_name: str, *, default: str | None = None, env: Mapping[str, str] | None = None
) -> str | None:
    source_env = env if env is not None else os.environ
    return source_env.get(env_name, default)


def _credential_ref_summary(credential_ref: str) -> str:
    if credential_ref.startswith("env:"):
        return credential_ref
    path = Path(credential_ref.removeprefix("file://"))
    prefix = "file:" if credential_ref.startswith("file://") else "path:"
    return f"{prefix}{path.name}"


def _record_definition_status(
    definition: ConnectorDefinition,
    result: ConnectorSyncResult,
    *,
    started_at: datetime,
) -> None:
    record_connector_status(
        connector_id=definition.connector_id,
        connector_type=definition.connector_type,
        tenant_id=definition.config.tenant_id,
        kb_id=definition.config.kb_id,
        status=result.status,
        summary=dict(result.summary),
        error=result.error,
        started_at=started_at,
        finished_at=_now(),
    )


def _google_config(definition: ConnectorDefinition) -> GoogleDriveConnectorConfig:
    if not isinstance(definition.config, GoogleDriveConnectorConfig):
        raise TypeError("connector is not a Google Drive connector")
    return definition.config


def _confluence_config(definition: ConnectorDefinition) -> ConfluenceConnectorConfig:
    if not isinstance(definition.config, ConfluenceConnectorConfig):
        raise TypeError("connector is not a Confluence connector")
    return definition.config


def _summary_dict(summary: Any) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in asdict(summary).items()
        if isinstance(value, int) and value != 0
    }


def _row_to_status(row: dict[str, object]) -> ConnectorStatus:
    return ConnectorStatus(
        connector_id=str(row["connector_id"]),
        connector_type=str(row["connector_type"]),
        tenant_id=str(row["tenant_id"]),
        kb_id=str(row["kb_id"]),
        last_status=str(row["last_status"]),
        last_started_at=_parse_datetime(row["last_started_at"]),
        last_finished_at=_parse_datetime(row["last_finished_at"]),
        last_summary=_load_summary(str(row["last_summary_json"])),
        last_error=str(row["last_error"]) if row["last_error"] is not None else None,
    )


def _load_summary(raw: str) -> dict[str, object]:
    loaded = json.loads(raw)
    return loaded if isinstance(loaded, dict) else {}


def _parse_datetime(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value is not None else None


def _sanitize_text(value: str) -> str:
    redacted = _SECRET_WORD_RE.sub(r"\1 [REDACTED]", value)
    return str(_redact_value(redacted))


async def _no_sleep(seconds: float) -> None:
    return None


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _database(database: SQLiteDatabase | None = None) -> SQLiteDatabase:
    if database is not None:
        return database
    from fleetent.knowledge_base import runtime

    return runtime._database()


def _kb_config(settings: ConnectorSettings | None = None) -> KnowledgeConfigSnapshot:
    """Normalize explicit connector settings into the snapshot shape operations expect."""
    if settings is None:
        raise ValueError("explicit connector settings are required")
    if isinstance(settings, KnowledgeConfigSnapshot):
        return settings
    if isinstance(settings, KnowledgeBaseSettings):
        return _snapshot_from_knowledge_settings(settings)
    knowledge_settings = getattr(settings, "knowledge_base", None)
    if isinstance(knowledge_settings, KnowledgeBaseSettings):
        return _snapshot_from_knowledge_settings(knowledge_settings)
    raise TypeError("connector settings must be a KnowledgeConfigSnapshot or KnowledgeBaseSettings")


def _snapshot_from_knowledge_settings(settings: KnowledgeBaseSettings) -> KnowledgeConfigSnapshot:
    kb_sources: dict[tuple[str, str], list[dict[str, object]]] = {}
    for connector in settings.google_drive.connectors:
        key = (connector.tenant_id, connector.kb_id)
        kb_sources.setdefault(key, []).append(
            {
                "id": connector.connector_id,
                "type": "google_drive",
                "enabled": connector.enabled,
                "folder_id": connector.folder_id,
                "recursive": connector.recursive,
                "credential_ref": connector.credential_ref,
                "access_token_env": connector.access_token_env,
                "refresh_token_env": connector.refresh_token_env,
                "client_id_env": connector.client_id_env,
                "client_secret_env": connector.client_secret_env,
                "token_uri_env": connector.token_uri_env,
            }
        )
    for connector in settings.confluence.connectors:
        key = (connector.tenant_id, connector.kb_id)
        kb_sources.setdefault(key, []).append(
            {
                "id": connector.connector_id,
                "type": "confluence",
                "enabled": connector.enabled,
                "base_url": connector.base_url,
                "username": connector.username,
                "username_env": connector.username_env,
                "credential_ref": connector.credential_ref,
                "api_token_env": connector.api_token_env,
                "scope_type": connector.scope_type,
                "space_key": connector.space_key,
                "page_id": connector.page_id,
                "include_children": connector.include_children,
            }
        )
    return KnowledgeConfigSnapshot.model_validate(
        {
            "knowledge_bases": [
                {"tenant_id": tenant_id, "id": kb_id, "sources": sources}
                for (tenant_id, kb_id), sources in kb_sources.items()
            ]
        }
    )
