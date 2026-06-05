from __future__ import annotations

import json
import platform
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fleetent import paths
from fleetent.agent_config import AgentFile
from fleetent.config import DiagnosticsSettings, Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.observability.performance import PerformanceQuery, get_performance_summary
from fleetent.observability.structured_logging import _redact_value
from fleetent.observability.traces import TraceEvent, TraceQuery, query_trace_events
from fleetent.observability.usage import UsageQuery, get_usage_summary

_MAX_TEXT_LENGTH = 2048
_SECRET_WORD_RE = re.compile(
    r"\b(token|secret|password|api[_-]?key|authorization|credential)[\s:=_-]+([^\s,;]+)",
    re.IGNORECASE,
)


def _default_data_dir() -> Path:
    return paths.data_dir()


@dataclass(frozen=True)
class DiagnosticsExportRequest:
    output_dir: Path | None = None
    log_dir: Path | None = None
    data_dir: Path | None = None
    secrets_dir: Path | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    include_logs: bool = True
    include_traces: bool = True
    include_connector_status: bool = True
    settings: AgentFile | None = None


@dataclass(frozen=True)
class DiagnosticsExportPackage:
    path: Path
    manifest_path: Path | None = None


@dataclass(frozen=True)
class DiagnosticsRetentionPlan:
    log_files: list[Path]
    trace_count: int
    diagnostic_exports: list[Path]


@dataclass(frozen=True)
class DiagnosticsRetentionResult:
    applied: bool
    deleted_logs: int
    deleted_traces: int
    deleted_exports: int
    failures: list[str]
    message: str


def export_diagnostics(request: DiagnosticsExportRequest | None = None) -> DiagnosticsExportPackage:
    """Create a local sanitized diagnostics package."""
    req = request or DiagnosticsExportRequest()
    from fleetent import agent_config

    settings = req.settings or agent_config.active_agent_or_default()
    now = datetime.now(UTC).replace(microsecond=0)
    start_ts = req.start_ts or now - timedelta(days=1)
    end_ts = req.end_ts or now
    output_dir = req.output_dir or Path(settings.diagnostics.export_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"diagnostics-{now.strftime('%Y%m%d-%H%M%S')}.zip"
    log_dir = req.log_dir or Path(settings.observability.logging.directory)
    data_dir = req.data_dir or _default_data_dir()

    artifact_names: list[str] = []
    skipped_artifacts = _forbidden_skips(data_dir, req.secrets_dir)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if req.include_logs:
            artifact_names.extend(_write_logs(archive, log_dir))
        if req.include_traces:
            artifact_names.extend(_write_traces(archive, start_ts, end_ts))
        if req.include_connector_status:
            artifact_names.extend(_write_connector_status(archive, settings))
        artifact_names.append(_write_json(archive, "environment.json", _environment_summary()))
        artifact_names.append(
            _write_json(archive, "config_summary.json", _config_summary(settings))
        )
        _write_json(
            archive,
            "exclusions.json",
            {
                "business_data": [
                    "memory",
                    "knowledge_documents",
                    "knowledge_chunks",
                    "sqlite_main_database",
                    "sqlite_backups",
                ],
                "data_dir": str(data_dir),
            },
        )
        artifact_names.append("exclusions.json")
        _write_json(
            archive,
            "manifest.json",
            {
                "artifacts": [
                    {"kind": _artifact_kind(name), "name": name, "redacted": True}
                    for name in sorted(artifact_names)
                ],
                "created_at": now.isoformat(),
                "includes": {
                    "connector_status": req.include_connector_status,
                    "logs": req.include_logs,
                    "traces": req.include_traces,
                },
                "redaction_version": 1,
                "skipped_artifacts": skipped_artifacts,
                "source_summary": {"data_dir": str(data_dir)},
                "time_range": {"from": start_ts.isoformat(), "to": end_ts.isoformat()},
            },
        )
    return DiagnosticsExportPackage(path=path, manifest_path=path)


def plan_diagnostics_retention(
    *,
    settings: DiagnosticsSettings | None = None,
    log_dir: Path | None = None,
    data_dir: Path | None = None,
    now: datetime | None = None,
) -> DiagnosticsRetentionPlan:
    """Plan diagnostics retention candidates without mutating data."""
    diagnostics = settings or _default_diagnostics()
    current = now or datetime.now(UTC)
    logs = _old_files(
        log_dir or _default_data_dir() / "logs",
        diagnostics.retention.logs_days,
        current,
        suffixes=(".log",),
    )
    exports = _old_files(
        Path(diagnostics.export_dir),
        diagnostics.retention.diagnostic_exports_days,
        current,
        suffixes=(".zip",),
    )
    trace_count = _old_trace_count(diagnostics.retention.traces_days, current)
    return DiagnosticsRetentionPlan(
        log_files=logs, trace_count=trace_count, diagnostic_exports=exports
    )


def apply_diagnostics_retention(
    *,
    settings: DiagnosticsSettings | None = None,
    log_dir: Path | None = None,
    data_dir: Path | None = None,
    now: datetime | None = None,
) -> DiagnosticsRetentionResult:
    """Apply manual diagnostics retention to logs, traces, and export packages."""
    diagnostics = settings or _default_diagnostics()
    if not diagnostics.retention.enabled:
        return DiagnosticsRetentionResult(False, 0, 0, 0, [], "diagnostics retention disabled")
    plan = plan_diagnostics_retention(
        settings=diagnostics,
        log_dir=log_dir,
        data_dir=data_dir,
        now=now,
    )
    deleted_logs, log_failures = _delete_files(plan.log_files)
    deleted_exports, export_failures = _delete_files(plan.diagnostic_exports)
    deleted_traces = _delete_old_traces(diagnostics.retention.traces_days, now or datetime.now(UTC))
    failures = [*log_failures, *export_failures]
    return DiagnosticsRetentionResult(
        True,
        deleted_logs,
        deleted_traces,
        deleted_exports,
        failures,
        "diagnostics retention applied",
    )


def _write_logs(archive: zipfile.ZipFile, log_dir: Path) -> list[str]:
    if not log_dir.exists():
        return []
    names = []
    for path in sorted(log_dir.glob("*.log")):
        name = f"logs/{path.name}"
        archive.writestr(name, _sanitize(path.read_text(encoding="utf-8")))
        names.append(name)
    return names


def _write_traces(archive: zipfile.ZipFile, start_ts: datetime, end_ts: datetime) -> list[str]:
    events = query_trace_events(TraceQuery(start_ts=start_ts, end_ts=end_ts, limit=10_000))
    event_lines: list[str] = []
    for event in events:
        event_lines.append(_event_json(event))
    archive.writestr(
        "traces/events.jsonl", "".join(event_lines), compress_type=zipfile.ZIP_DEFLATED
    )
    try:
        usage_summary = asdict(get_usage_summary(UsageQuery(start_ts=start_ts, end_ts=end_ts)))
    except Exception:
        usage_summary = {}
    try:
        performance_summary = asdict(
            get_performance_summary(PerformanceQuery(start_ts=start_ts, end_ts=end_ts))
        )
    except Exception:
        performance_summary = {}
    return [
        "traces/events.jsonl",
        _write_json(archive, "traces/usage_summary.json", usage_summary),
        _write_json(
            archive,
            "traces/performance_summary.json",
            performance_summary,
        ),
    ]


def _write_connector_status(archive: zipfile.ZipFile, settings: AgentFile) -> list[str]:
    connectors = list_configured_connectors(settings=settings)
    status_payload = []
    for connector in connectors:
        connector_id = getattr(connector, "connector_id", None)
        latest_status = None
        if connector_id:
            try:
                latest_status = get_connector_status(str(connector_id), settings=settings)
            except Exception as exc:
                latest_status = {
                    "connector_id": str(connector_id),
                    "last_status": "status_unavailable",
                    "last_error": str(exc),
                }
        status_payload.append(
            {
                "connector": _safe_dataclass(connector),
                "status": _safe_dataclass(latest_status) if latest_status is not None else None,
            }
        )
    return [
        _write_json(
            archive,
            "knowledge_connectors/status.json",
            status_payload,
        )
    ]


def list_configured_connectors(settings: AgentFile | None = None) -> list[object]:
    from fleetent.intelligence.knowledge_base.operations import (
        list_configured_connectors as list_kb_connectors,
    )

    return list(list_kb_connectors(settings=settings))


def get_connector_status(connector_id: str, settings: AgentFile | None = None) -> object:
    from fleetent.intelligence.knowledge_base.operations import (
        get_connector_status as get_kb_connector_status,
    )

    return get_kb_connector_status(connector_id, settings=settings)


def _event_json(event: TraceEvent) -> str:
    payload = _truncate(_redact_value(event.payload))
    return (
        json.dumps(
            {
                "id": event.id,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "ts": event.ts.isoformat() if event.ts else None,
                "tenant_id": event.tenant_id,
                "agent_id": event.agent_id,
                "user_id": event.user_id,
                "payload": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    )


def _write_json(archive: zipfile.ZipFile, name: str, payload: object) -> str:
    archive.writestr(
        name,
        json.dumps(
            _truncate(_redact_value(payload)), ensure_ascii=False, sort_keys=True, default=str
        ),
    )
    return name


def _forbidden_skips(data_dir: Path, secrets_dir: Path | None) -> list[dict[str, str]]:
    skipped: list[dict[str, str]] = []
    if data_dir.exists():
        for path in sorted(data_dir.iterdir()):
            if path.is_file() and (
                path.suffix in {".db", ".sqlite", ".sqlite3"} or ".db" in path.name
            ):
                skipped.append({"name": f"data/{path.name}", "reason": "sqlite database excluded"})
    if secrets_dir and secrets_dir.exists():
        for path in sorted(secrets_dir.iterdir()):
            if path.is_file():
                skipped.append({"name": f"secrets/{path.name}", "reason": "secret file excluded"})
    return skipped


def _artifact_kind(name: str) -> str:
    if name.startswith("logs/"):
        return "log_summary"
    if name.startswith("traces/"):
        return "trace_summary"
    if name.startswith("knowledge_connectors/"):
        return "connector_summary"
    return "summary"


def _environment_summary() -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }


def _config_summary(settings: AgentFile) -> dict[str, object]:
    return {
        "database_url": _database_url_summary(_settings().database_url),
        "observability": {"log_dir": settings.observability.logging.directory},
        "diagnostics": {
            "export_dir": settings.diagnostics.export_dir,
            "retention_enabled": settings.diagnostics.retention.enabled,
            "logs_days": settings.diagnostics.retention.logs_days,
            "traces_days": settings.diagnostics.retention.traces_days,
            "diagnostic_exports_days": settings.diagnostics.retention.diagnostic_exports_days,
        },
        "knowledge_base": {"enabled": settings.knowledge_base.enabled},
    }


def _database_url_summary(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        return "sqlite:///<local-file>"
    return database_url.split("://", maxsplit=1)[0]


def _safe_dataclass(value: Any) -> object:
    return asdict(value) if hasattr(value, "__dataclass_fields__") else value


def _sanitize(value: str) -> str:
    redacted = _SECRET_WORD_RE.sub(r"\1 [REDACTED]", value)
    redacted = redacted.replace("secret [REDACTED] excluded", "secret file excluded")
    return str(_redact_value(redacted))


def _truncate(value: Any) -> Any:
    if isinstance(value, str):
        sanitized = _sanitize(value)
        if len(sanitized) > _MAX_TEXT_LENGTH:
            return {
                "value": sanitized[:_MAX_TEXT_LENGTH],
                "truncated": True,
                "original_length": len(sanitized),
            }
        return sanitized
    if isinstance(value, dict):
        return {str(key): _truncate(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncate(item) for item in value]
    return value


def _old_files(
    directory: Path, days: int | None, now: datetime, *, suffixes: tuple[str, ...]
) -> list[Path]:
    if days is None or not directory.exists():
        return []
    cutoff = now.timestamp() - days * 24 * 60 * 60
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix in suffixes and path.stat().st_mtime < cutoff
    )


def _old_trace_count(days: int | None, now: datetime) -> int:
    if days is None:
        return 0
    cutoff = (now - timedelta(days=days)).isoformat()
    try:
        row = (
            _database()
            .execute(
                "SELECT COUNT(*) AS count FROM traces WHERE ts < :cutoff",
                {"cutoff": cutoff},
            )
            .fetchone()
        )
    except Exception:
        return 0
    return int(row["count"]) if row else 0


def _delete_old_traces(days: int | None, now: datetime) -> int:
    if days is None:
        return 0
    cutoff = (now - timedelta(days=days)).isoformat()
    try:
        result = _database().execute("DELETE FROM traces WHERE ts < :cutoff", {"cutoff": cutoff})
    except Exception:
        return 0
    return result.rowcount


def _delete_files(paths: list[Path]) -> tuple[int, list[str]]:
    deleted = 0
    failures: list[str] = []
    for path in paths:
        try:
            path.unlink()
            deleted += 1
        except Exception as exc:
            failures.append(f"{path.name}: {exc}")
    return deleted, failures


def _settings() -> Settings:
    return Settings(anthropic_api_key="")


def _default_diagnostics() -> DiagnosticsSettings:
    """Diagnostics config from the active agent (a neutral default when absent)."""
    from fleetent import agent_config

    return agent_config.active_agent_or_default().diagnostics


def _database() -> SQLiteDatabase:
    return create_database(_settings().database_url)
