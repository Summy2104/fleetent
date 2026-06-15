"""Agent run trace public API."""

import json
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from fleetent import paths
from fleetent.db import SQLiteDatabase, create_database
from fleetent.integrations.sandbox import is_sensitive_name
from fleetent.structured_logging import _redact_value, get_logger

_MAX_STRING_LENGTH = 2048
_MAX_SEQUENCE_LENGTH = 50
_RAW_CONTENT_KEYS = frozenset({"content", "text", "transcript"})

# args_summary upper bound (D2): serialized tool args are truncated to this many
# characters (marker included) so a tool_call event can never bloat the trace.
_ARGS_SUMMARY_MAX_LENGTH = 2048
_ARGS_SUMMARY_TRUNCATION_MARKER = "...[truncated]"
_REDACTED_ARG_PLACEHOLDER = "[REDACTED]"

_logger = get_logger("observability.traces")

_state_db: SQLiteDatabase | None = None


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB.  Called once at agent boot via agent_app."""
    global _state_db
    _state_db = db


def _db() -> SQLiteDatabase:
    """Return the per-agent state DB if injected, else fall back to DATABASE_URL (platform path)."""
    if _state_db is not None:
        return _state_db
    return create_database(_database_url())


@dataclass(frozen=True)
class TraceEvent:
    """Agent run trace event."""

    run_id: str
    event_type: str
    payload: dict[str, Any]
    id: str | None = None
    ts: datetime | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    agent_name: str | None = None
    tenant_id: str = "default"


@dataclass(frozen=True)
class TraceQuery:
    """Agent run trace query."""

    run_id: str | None = None
    user_id: str | None = None
    agent_name: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    event_type: str | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    limit: int = 100


@dataclass(frozen=True)
class InjectedContextTrace:
    """Summary of a source injected into an agent prompt."""

    source_id: str
    source_type: Literal["memory", "knowledge"]
    score: float
    token_estimate: int
    metadata: dict[str, str]


def record_injected_context(
    run_id: str, sources: list[InjectedContextTrace], session_id: str | None = None
) -> None:
    """Record source summaries for long-term context injected into a prompt."""
    if not sources:
        return
    record_trace_event(
        TraceEvent(
            run_id=run_id,
            event_type="injected_context",
            payload={"sources": [_source_summary(source) for source in sources]},
            session_id=session_id,
        )
    )


def _source_summary(source: InjectedContextTrace) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "source_type": source.source_type,
        "score": source.score,
        "token_estimate": source.token_estimate,
        "metadata": {
            key: value
            for key, value in source.metadata.items()
            if key.lower() not in _RAW_CONTENT_KEYS
        },
    }


def record_tool_call(run_id: str, session_id: str | None, payload: dict[str, Any]) -> None:
    """Record one ``tool_call`` trace event for a tool that really executed.

    Best-effort by contract: a write failure (DB unavailable, etc.) is logged at
    warning and swallowed — observability is a side channel and MUST NOT affect the
    tool result or the run. The caller builds ``payload`` (tool_name, tool_call_id,
    args_summary, failed, duration_ms, risk); ``session_id`` binds the event to its
    conversation when available.
    """
    try:
        record_trace_event(
            TraceEvent(
                run_id=run_id,
                event_type="tool_call",
                payload=payload,
                session_id=session_id,
            )
        )
    except Exception as exc:  # noqa: BLE001 — side channel; never break the run
        _logger.warn("tool_call_trace_record_failed", run_id=run_id, error=str(exc))


def mask_target(target: str | None) -> str:
    """Mask a delivery target id for trace/trailer display (delivery-receipts, D3).

    Keeps a short head+tail so a human can sanity-check the recipient without exposing the
    full platform id: ``U0123456789`` → ``U01…789``. Short ids pass through unchanged.
    """
    t = str(target or "")
    if len(t) <= 6:
        return t
    return f"{t[:3]}…{t[-3:]}"


def render_delivery_trailer(ledger: list[Any] | None) -> str | None:
    """Render the run's delivery ledger into a one-line fact trailer, or None if empty (§3, D4).

    Deterministic system output appended after the model's final reply so the ground truth
    of what was delivered sits beside the model's claim. Compact: success file/message
    counts with masked target summaries + a failure list. Duck-typed over DeliveryReceipt
    (.ok/.kind/.target/.error) to avoid an outbound import. None ledger / no attempts → None.
    """
    if not ledger:
        return None
    files_ok = [r for r in ledger if r.kind == "file" and r.ok]
    msgs_ok = [r for r in ledger if r.kind == "text" and r.ok]
    failed = [r for r in ledger if not r.ok]
    parts: list[str] = []
    if files_ok:
        tgts = ", ".join(mask_target(r.target) for r in files_ok)
        parts.append(f"文件 {len(files_ok)}（{tgts}）")
    if msgs_ok:
        tgts = ", ".join(mask_target(r.target) for r in msgs_ok)
        parts.append(f"消息 {len(msgs_ok)}（{tgts}）")
    if failed:
        reasons = ", ".join(str(r.error or "?") for r in failed)
        parts.append(f"失败 {len(failed)}（{reasons}）")
    return "📬 实际投递：" + "；".join(parts)


def record_delivery(run_id: str, session_id: str | None, payload: dict[str, Any]) -> None:
    """Record one ``delivery`` trace event for an outbound delivery attempt (best-effort).

    Mirrors ``record_tool_call``: a write failure is logged at warning and swallowed
    (side channel, never affects the run). The caller builds ``payload`` from a
    DeliveryReceipt (ok, platform, target, target_type, kind, provider_ref, error); the
    ``target`` is masked here so the audit trail never carries the full recipient id.
    """
    try:
        masked = dict(payload)
        if "target" in masked:
            masked["target"] = mask_target(masked.get("target"))
        record_trace_event(
            TraceEvent(
                run_id=run_id,
                event_type="delivery",
                payload=masked,
                session_id=session_id,
            )
        )
    except Exception as exc:  # noqa: BLE001 — side channel; never break the run
        _logger.warn("delivery_trace_record_failed", run_id=run_id, error=str(exc))


def build_tool_args_summary(tool_args: dict[str, Any] | str) -> str:
    """Redact and bound a tool's arguments into a trace-safe summary string.

    Top-level argument names matching the sensitive-name baseline (SB5
    ``is_sensitive_name``) have their values replaced before serialization, then the
    JSON is truncated to a fixed cap with a marker (D2). Value-level redaction of
    secrets embedded in benign-named fields is layered on by ``record_trace_event``.
    """
    parsed: Any
    if isinstance(tool_args, str):
        try:
            parsed = json.loads(tool_args)
        except (json.JSONDecodeError, ValueError):
            parsed = None
    else:
        parsed = tool_args
    if isinstance(parsed, dict):
        redacted = {
            str(key): (_REDACTED_ARG_PLACEHOLDER if is_sensitive_name(str(key)) else value)
            for key, value in parsed.items()
        }
        # default=str: a non-serializable value (e.g. an out-of-band injected ToolContext)
        # degrades to its string form rather than raising — a trace summary must never crash
        # its caller (fix-approval-resume-serialization).
        text = json.dumps(redacted, ensure_ascii=False, sort_keys=True, default=str)
    elif isinstance(tool_args, str):
        text = tool_args
    else:
        text = json.dumps(tool_args, ensure_ascii=False, sort_keys=True, default=str)
    if len(text) > _ARGS_SUMMARY_MAX_LENGTH:
        keep = _ARGS_SUMMARY_MAX_LENGTH - len(_ARGS_SUMMARY_TRUNCATION_MARKER)
        text = text[:keep] + _ARGS_SUMMARY_TRUNCATION_MARKER
    return text


def record_trace_event(event: TraceEvent) -> None:
    """Record one agent run trace event."""
    event_id = event.id or str(uuid.uuid4())
    ts = event.ts or datetime.now(UTC)
    payload = _prepare_payload(event.payload)
    _db().execute(
        """
        INSERT INTO traces (
            id, run_id, span_id, parent_span_id, session_id, user_id, agent_name,
            tenant_id, event_type, ts, payload_json
        ) VALUES (
            :id, :run_id, :span_id, :parent_span_id, :session_id, :user_id, :agent_name,
            :tenant_id, :event_type, :ts, :payload_json
        )
        """,
        {
            "id": event_id,
            "run_id": event.run_id,
            "span_id": event.span_id,
            "parent_span_id": event.parent_span_id,
            "session_id": event.session_id,
            "user_id": event.user_id,
            "agent_name": event.agent_name,
            "tenant_id": event.tenant_id,
            "event_type": event.event_type,
            "ts": ts.isoformat(),
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    )


def query_trace_events(query: TraceQuery) -> Iterator[TraceEvent]:
    """Query agent run trace events."""
    clauses: list[str] = []
    params: dict[str, object] = {"limit": query.limit}
    for field in ("run_id", "user_id", "agent_name", "session_id", "tenant_id", "event_type"):
        value = getattr(query, field)
        if value is not None:
            clauses.append(f"{field} = :{field}")
            params[field] = value
    if query.start_ts is not None:
        clauses.append("ts >= :start_ts")
        params["start_ts"] = query.start_ts.isoformat()
    if query.end_ts is not None:
        clauses.append("ts <= :end_ts")
        params["end_ts"] = query.end_ts.isoformat()

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _db().execute(
        f"""
        SELECT
            id, run_id, span_id, parent_span_id, session_id, user_id, agent_name,
            tenant_id, event_type, ts, payload_json
        FROM traces
        {where}
        ORDER BY ts ASC
        LIMIT :limit
        """,
        params,
    )
    return (_trace_event_from_row(row) for row in rows.fetchall())


def _database_url() -> str:
    default = f"sqlite:///{paths.data_dir() / 'management.db'}"
    return os.environ.get("DATABASE_URL", default)


def _prepare_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = _redact_value(payload)
    safe_payload, used_fallback = _json_safe(redacted)
    truncated_payload, was_truncated = _truncate_value(safe_payload)
    if not isinstance(truncated_payload, dict):
        truncated_payload = {"value": truncated_payload}
    if used_fallback:
        truncated_payload["serialization_fallback"] = True
    if was_truncated:
        truncated_payload["truncated"] = True
    return truncated_payload


def _json_safe(value: Any) -> tuple[Any, bool]:
    if isinstance(value, dict):
        used_fallback = False
        safe: dict[str, Any] = {}
        for key, item in value.items():
            safe_item, item_fallback = _json_safe(item)
            safe[str(key)] = safe_item
            used_fallback = used_fallback or item_fallback
        return safe, used_fallback
    if isinstance(value, list):
        used_fallback = False
        safe_list: list[Any] = []
        for item in value:
            safe_item, item_fallback = _json_safe(item)
            safe_list.append(safe_item)
            used_fallback = used_fallback or item_fallback
        return safe_list, used_fallback
    if isinstance(value, tuple):
        safe_value, used_fallback = _json_safe(list(value))
        return safe_value, used_fallback
    try:
        json.dumps(value)
    except TypeError:
        return str(value), True
    return value, False


def _truncate_value(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str) and len(value) > _MAX_STRING_LENGTH:
        half = _MAX_STRING_LENGTH // 2
        return {
            "value": f"{value[:half]}...{value[-half:]}",
            "truncated": True,
            "original_length": len(value),
        }, True
    if isinstance(value, dict):
        truncated = False
        result: dict[str, Any] = {}
        for key, item in value.items():
            result[key], item_truncated = _truncate_value(item)
            truncated = truncated or item_truncated
        return result, truncated
    if isinstance(value, list):
        items = value
        truncated = False
        if len(value) > _MAX_SEQUENCE_LENGTH:
            keep = _MAX_SEQUENCE_LENGTH // 2
            items = [*value[:keep], *value[-keep:]]
            truncated = True
        list_result: list[Any] = []
        for item in items:
            truncated_item, item_truncated = _truncate_value(item)
            list_result.append(truncated_item)
            truncated = truncated or item_truncated
        if len(value) > _MAX_SEQUENCE_LENGTH:
            return {
                "items": list_result,
                "truncated": True,
                "original_length": len(value),
            }, True
        return list_result, truncated
    return value, False


def _trace_event_from_row(row: dict[str, Any]) -> TraceEvent:
    return TraceEvent(
        id=row["id"],
        run_id=row["run_id"],
        span_id=row["span_id"],
        parent_span_id=row["parent_span_id"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        agent_name=row["agent_name"],
        tenant_id=row["tenant_id"],
        event_type=row["event_type"],
        ts=datetime.fromisoformat(row["ts"]),
        payload=json.loads(row["payload_json"]),
    )
