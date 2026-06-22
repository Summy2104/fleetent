"""Per-KB observation aggregation over existing kb_retrieval traces."""

from __future__ import annotations

from typing import Any

from fleetent import agent_store
from fleetent.observability.traces import TraceQuery, query_trace_events

DEFAULT_LIMIT = 10_000


def aggregate(tenant_id: str, kb_id: str, bound_agent_ids: list[int]) -> dict[str, Any]:
    """Aggregate proxy retrieval metrics for one KB across its bound agents."""
    resolved_agents = [
        (agent_id, agent_name)
        for agent_id in sorted(bound_agent_ids)
        if (agent_name := agent_store.get_agent_name_by_id(agent_id)) is not None
    ]
    events = [
        event
        for _, agent_name in resolved_agents
        for event in query_trace_events(
            TraceQuery(
                tenant_id=tenant_id,
                agent_name=agent_name,
                event_type="kb_retrieval",
                limit=DEFAULT_LIMIT,
            )
        )
        if _event_matches_kb(event.payload, kb_id)
    ]

    latencies = [_to_float(event.payload.get("latency_ms")) for event in events]
    latency_samples = [sample for sample in latencies if sample is not None]
    total_hits = sum(_to_int(event.payload.get("hit_count")) for event in events)
    zero_recall_count = sum(1 for event in events if _to_int(event.payload.get("hit_count")) == 0)
    score_samples = [
        score
        for event in events
        for score in _scores(event.payload.get("scores"))
    ]
    sessions = sorted({event.session_id for event in events if event.session_id})

    return {
        "kb_id": kb_id,
        "bound_agents": [agent_id for agent_id, _ in resolved_agents],
        "query_count": len(events),
        "hit_count": total_hits,
        "zero_recall_rate": (zero_recall_count / len(events)) if events else 0.0,
        "latency_ms": {
            "p50": _percentile(latency_samples, 50),
            "p95": _percentile(latency_samples, 95),
        },
        "score_distribution": {
            "count": len(score_samples),
            "min": min(score_samples) if score_samples else None,
            "p50": _percentile(score_samples, 50) if score_samples else None,
            "p95": _percentile(score_samples, 95) if score_samples else None,
            "max": max(score_samples) if score_samples else None,
        },
        "sessions": sessions,
    }


def _event_matches_kb(payload: dict[str, Any], kb_id: str) -> bool:
    if payload.get("kb_id") == kb_id:
        return True
    kb_ids = payload.get("kb_ids")
    return isinstance(kb_ids, list) and kb_id in kb_ids


def _scores(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    return [score for item in value if (score := _to_float(item)) is not None]


def _to_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _percentile(samples: list[float], percentile: int) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, (percentile * len(ordered) + 99) // 100 - 1))
    return ordered[index]
