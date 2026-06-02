"""Per-agent observability: read-only aggregation over agent run traces.

This module never records anything — it consumes the existing trace store and rolls
events up per agent for the console (calls / tokens / cost / error-rate / latency /
approval pass-rate / recent sessions) plus a single-run drill-down. Trace access goes
through ``query_trace_events`` so tests can mock the source without a DB.
"""

import datetime
from typing import Any

from fleetent.observability.traces import TraceQuery, query_trace_events

# Self-hosted models are typically free; pricing is configurable / monkeypatchable.
COST_PER_1K_TOKENS = 0.0
DEFAULT_LIMIT = 1000
RECENT_SESSIONS = 20

_WINDOWS = {
    "1h": datetime.timedelta(hours=1),
    "24h": datetime.timedelta(hours=24),
    "7d": datetime.timedelta(days=7),
    "30d": datetime.timedelta(days=30),
}


def _window_delta(window: str) -> datetime.timedelta:
    return _WINDOWS.get(window, _WINDOWS["24h"])


def aggregate(
    agent_id: str, window: str = "24h", now: datetime.datetime | None = None
) -> dict[str, Any]:
    """Roll up trace events for one agent over a time window."""
    moment = now or datetime.datetime.now(datetime.UTC)
    start = moment - _window_delta(window)
    events = list(
        query_trace_events(
            TraceQuery(agent_id=agent_id, start_ts=start, end_ts=moment, limit=DEFAULT_LIMIT)
        )
    )

    completed = [e for e in events if e.event_type == "agent_run_completed"]
    failed = [e for e in events if e.event_type == "agent_run_failed"]
    runs = len(completed) + len(failed)

    tokens = sum(_total_tokens(e.payload) for e in completed)
    latencies = [e.payload["elapsed_s"] for e in completed if "elapsed_s" in e.payload]

    resolved = [e for e in events if e.event_type == "permission_resolved"]
    approved = [e for e in resolved if e.payload.get("decision") == "approved"]
    requested = [e for e in events if e.event_type == "permission_requested"]

    return {
        "agent_name": agent_id,
        "window": window,
        "calls": runs,
        "tokens": tokens,
        "cost": round(tokens / 1000 * COST_PER_1K_TOKENS, 6),
        "error_rate": (len(failed) / runs) if runs else 0.0,
        "avg_latency": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "approvals_triggered": len(requested),
        "approval_pass_rate": (len(approved) / len(resolved)) if resolved else None,
        "recent_sessions": _recent_sessions(completed, failed),
    }


def drill_down(run_id: str) -> list[dict[str, Any]]:
    """Return the ordered event chain for a single run (session drill-down)."""
    events = list(query_trace_events(TraceQuery(run_id=run_id, limit=DEFAULT_LIMIT)))
    events.sort(key=lambda e: e.ts or datetime.datetime.min.replace(tzinfo=datetime.UTC))
    return [
        {"event_type": e.event_type, "ts": e.ts.isoformat() if e.ts else None, "payload": e.payload}
        for e in events
    ]


def _total_tokens(payload: dict[str, Any]) -> int:
    tokens = payload.get("tokens")
    return int(tokens["total"]) if isinstance(tokens, dict) and tokens.get("total") else 0


def _recent_sessions(completed: list[Any], failed: list[Any]) -> list[dict[str, Any]]:
    rows = [(e, "completed") for e in completed] + [(e, "failed") for e in failed]
    rows.sort(
        key=lambda pair: pair[0].ts or datetime.datetime.min.replace(tzinfo=datetime.UTC),
        reverse=True,
    )
    return [
        {
            "run_id": e.run_id,
            "session_id": e.session_id,
            "status": status,
            "ts": e.ts.isoformat() if e.ts else None,
        }
        for e, status in rows[:RECENT_SESSIONS]
    ]
