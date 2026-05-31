"""Agent run trace public API."""

import json
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from fleetent.db import create_database
from fleetent.observability.structured_logging import _redact_value

_MAX_STRING_LENGTH = 2048
_MAX_SEQUENCE_LENGTH = 50
_RAW_CONTENT_KEYS = frozenset({"content", "text", "transcript"})


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
    agent_id: str | None = None
    tenant_id: str = "default"


@dataclass(frozen=True)
class TraceQuery:
    """Agent run trace query."""

    run_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
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


def record_injected_context(run_id: str, sources: list[InjectedContextTrace]) -> None:
    """Record source summaries for long-term context injected into a prompt."""
    if not sources:
        return
    record_trace_event(
        TraceEvent(
            run_id=run_id,
            event_type="injected_context",
            payload={"sources": [_source_summary(source) for source in sources]},
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


def record_trace_event(event: TraceEvent) -> None:
    """Record one agent run trace event."""
    event_id = event.id or str(uuid.uuid4())
    ts = event.ts or datetime.now(UTC)
    payload = _prepare_payload(event.payload)
    database = create_database(_database_url())
    database.execute(
        """
        INSERT INTO traces (
            id, run_id, span_id, parent_span_id, session_id, user_id, agent_id,
            tenant_id, event_type, ts, payload_json
        ) VALUES (
            :id, :run_id, :span_id, :parent_span_id, :session_id, :user_id, :agent_id,
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
            "agent_id": event.agent_id,
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
    for field in ("run_id", "user_id", "agent_id", "tenant_id", "event_type"):
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
    rows = create_database(_database_url()).execute(
        f"""
        SELECT
            id, run_id, span_id, parent_span_id, session_id, user_id, agent_id,
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
    return os.environ.get("DATABASE_URL", "sqlite:///data/users.db")


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
        agent_id=row["agent_id"],
        tenant_id=row["tenant_id"],
        event_type=row["event_type"],
        ts=datetime.fromisoformat(row["ts"]),
        payload=json.loads(row["payload_json"]),
    )
