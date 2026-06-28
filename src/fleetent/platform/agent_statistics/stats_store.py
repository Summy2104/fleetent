"""Pure aggregation helpers for the Agent statistics panel.

These functions take already-fetched trace records (list of dicts) and compute
read-only aggregations. They do not touch the DB or emit anything — the panel is an
aggregation layer over observability traces / approvals / agent_store, which the API
fetches through injectable seams. Keeping the math pure makes it trivially testable.

Trace records are read defensively with .get() so partial / ⏳-not-yet-emitted fields
degrade to placeholders rather than errors.
"""

import csv
import fnmatch
import io
from collections import Counter, defaultdict
from typing import Any

UNCONFIGURED = "未配置"
PENDING_DATA = "待数据接入"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def aggregate_usage(traces: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = sum(int(t.get("prompt_tokens", 0)) for t in traces)
    completion = sum(int(t.get("completion_tokens", 0)) for t in traces)
    total = sum(int(t.get("total_tokens", t.get("tokens", 0))) for t in traces)
    calls = len(traces)
    return {
        "calls": calls,
        "users": len({t.get("user_id") for t in traces if t.get("user_id")}),
        "channels": len({t.get("channel") for t in traces if t.get("channel")}),
        "sessions": len({t.get("session_id") for t in traces if t.get("session_id")}),
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "avg_total_tokens": round(total / calls, 2) if calls else 0,
    }


def aggregate_performance(traces: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(t["elapsed_s"]) for t in traces if t.get("elapsed_s") is not None]
    rounds = [int(t.get("rounds", 0)) for t in traces]
    return {
        "latency_avg": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "latency_p50": round(_percentile(latencies, 0.5), 3),
        "latency_p95": round(_percentile(latencies, 0.95), 3),
        "avg_rounds": round(sum(rounds) / len(rounds), 2) if rounds else 0.0,
    }


def _tool_names(trace: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for msg in trace.get("messages", []) or []:
        for call in msg.get("tool_calls", []) or []:
            name = call.get("name")
            if name:
                names.append(name)
    return names


def top_tools(traces: list[dict[str, Any]], limit: int = 10) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    total_calls = 0
    for t in traces:
        names = _tool_names(t)
        counter.update(names)
        total_calls += len(names)
    runs = len(traces) or 1
    return {
        "top": counter.most_common(limit),
        "avg_tools_per_run": round(total_calls / runs, 2),
    }


def allowed_tools_coverage(traces: list[dict[str, Any]], allowed: list[str]) -> dict[str, Any]:
    """Patterns in the allowlist that were never matched by an actual call this period."""
    used: set[str] = set()
    for t in traces:
        used.update(_tool_names(t))
    unused = [pat for pat in allowed if not any(fnmatch.fnmatch(u, pat) for u in used)]
    return {"allowed": allowed, "used": sorted(used), "unused_patterns": unused}


def approval_stats(approvals: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(approvals)
    if total == 0:
        return {"triggered": 0, "pass_rate": None, "reject_rate": None, "timeout_rate": None}
    counts = Counter(a.get("decision", "unknown") for a in approvals)
    return {
        "triggered": total,
        "pass_rate": round(counts.get("approved", 0) / total, 3),
        "reject_rate": round(counts.get("rejected", 0) / total, 3),
        "timeout_rate": round(counts.get("timeout", 0) / total, 3),
    }


def compare_agents(metrics_by_agent: dict[str, dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Stable ordering: primary metric desc, ties broken by agent_id asc."""
    rows = [{"agent_id": aid, **m} for aid, m in metrics_by_agent.items()]
    return sorted(rows, key=lambda r: (-(r.get(key) or 0), r["agent_id"]))


def per_user_ranking(
    traces: list[dict[str, Any]], sort_by: str = "total_tokens"
) -> list[dict[str, Any]]:
    by_user: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total_tokens": 0, "calls": 0, "days": set(), "last_active": None}
    )
    for t in traces:
        uid = t.get("user_id")
        if not uid:
            continue
        rec = by_user[uid]
        rec["total_tokens"] += int(t.get("total_tokens", t.get("tokens", 0)))
        rec["calls"] += 1
        ts = t.get("ts")
        if ts:
            rec["days"].add(ts[:10])
            if rec["last_active"] is None or ts > rec["last_active"]:
                rec["last_active"] = ts
    rows = [
        {
            "user_id": uid,
            "total_tokens": r["total_tokens"],
            "calls": r["calls"],
            "active_days": len(r["days"]),
            "last_active": r["last_active"],
        }
        for uid, r in by_user.items()
    ]
    return sorted(rows, key=lambda r: (-(r.get(sort_by) or 0), r["user_id"]))


def cost(
    traces: list[dict[str, Any]], pricing: dict[str, dict[str, float | None]] | None
) -> dict[str, Any]:
    """Cost = tokens × per-1k price. Unset price → 未配置; no pricing table → 待数据接入."""
    if pricing is None:
        return {"status": PENDING_DATA, "by_model": {}}
    by_model: dict[str, Any] = {}
    for t in traces:
        model = t.get("model_used", "unknown")
        entry = by_model.setdefault(model, {"prompt_tokens": 0, "completion_tokens": 0})
        entry["prompt_tokens"] += int(t.get("prompt_tokens", 0))
        entry["completion_tokens"] += int(t.get("completion_tokens", 0))
    for model, entry in by_model.items():
        price = pricing.get(model)
        if price is None or price.get("input") is None or price.get("output") is None:
            entry["cost"] = UNCONFIGURED
        else:
            entry["cost"] = round(
                entry["prompt_tokens"] / 1000 * price["input"]
                + entry["completion_tokens"] / 1000 * price["output"],
                4,
            )
    return {"status": "ok", "by_model": by_model}


def build_request_list(traces: list[dict[str, Any]], user_id: str) -> list[dict[str, Any]]:
    rows = [
        {
            "request_id": t.get("request_id"),
            "session_id": t.get("session_id"),
            "ts": t.get("ts"),
            "agent_id": t.get("agent_id") or t.get("agent_name"),
            "channel": t.get("channel"),
            "total_tokens": int(t.get("total_tokens", t.get("tokens", 0))),
            "elapsed_s": t.get("elapsed_s"),
            "status": t.get("status", "ok"),
        }
        for t in traces
        if t.get("user_id") == user_id
    ]
    return sorted(rows, key=lambda r: r.get("ts") or "")


def build_event_stream(traces: list[dict[str, Any]], request_id: str) -> dict[str, Any]:
    events = sorted(
        (t for t in traces if t.get("request_id") == request_id),
        key=lambda t: t.get("ts") or "",
    )
    return {"request_id": request_id, "events": events, "complete": True}


def build_event_stream_degraded(
    traces: list[dict[str, Any]], session_id: str, user_id: str
) -> dict[str, Any]:
    """Fallback when request_id was never emitted: group by session_id (+user_id)."""
    events = sorted(
        (t for t in traces if t.get("session_id") == session_id and t.get("user_id") == user_id),
        key=lambda t: t.get("ts") or "",
    )
    return {
        "session_id": session_id,
        "events": events,
        "complete": False,
        "note": "链路可能不完整（缺 request_id，按会话退化关联）",
    }


def expand_subagents(
    stream: dict[str, Any], traces: list[dict[str, Any]], note_when_empty: bool = False
) -> dict[str, Any]:
    """Attach sub_agent child chains, linked by parent_session_id."""
    linked = False
    for event in stream.get("events", []):
        sid = event.get("session_id")
        children = [t for t in traces if t.get("parent_session_id") == sid]
        if children:
            event["sub_agent_chain"] = sorted(children, key=lambda t: t.get("ts") or "")
            linked = True
    if note_when_empty and not linked:
        stream["sub_agent_note"] = "无法关联子链路"
    return stream


def model_distribution(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Calls / tokens split by model and by task_type."""

    def _bucket(key: str) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "total_tokens": 0})
        for t in traces:
            label = t.get(key, "unknown")
            rec = out[label]
            rec["calls"] += 1
            rec["total_tokens"] += int(t.get("total_tokens", t.get("tokens", 0)))
        return dict(out)

    return {"by_model": _bucket("model_used"), "by_task_type": _bucket("task_type")}


def binding_facts(
    bindings: int, default_agent: str | None, states: list[dict[str, Any]]
) -> dict[str, Any]:
    """Binding count + default agent across agent states."""
    return {
        "bindings": bindings,
        "default_agent": default_agent,
    }


def slice_traces(
    traces: list[dict[str, Any]],
    user_id: str | None = None,
    channel: str | None = None,
    model: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    """Filter traces by any combination of dimensions; ts bounds inclusive."""
    out = []
    for t in traces:
        if user_id is not None and t.get("user_id") != user_id:
            continue
        if channel is not None and t.get("channel") != channel:
            continue
        if model is not None and t.get("model_used") != model:
            continue
        ts = t.get("ts")
        if since is not None and (ts is None or ts < since):
            continue
        if until is not None and (ts is None or ts > until):
            continue
        out.append(t)
    return out


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """Serialize aggregation rows to CSV; header from first row's keys. Empty => ''."""
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def field_readiness(traces: list[dict[str, Any]], fields: list[str]) -> dict[str, str]:
    """A field is 'ready' once any trace carries it; else 待数据接入 placeholder."""
    return {
        field: "ready" if any(t.get(field) is not None for t in traces) else PENDING_DATA
        for field in fields
    }
