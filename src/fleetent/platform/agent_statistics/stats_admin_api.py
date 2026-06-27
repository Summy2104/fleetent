"""FastAPI router for /admin/stats — the Agent statistics panel (read-only).

An aggregation layer over observability traces / approvals / agent_store. It fetches
data through injectable seams and runs the pure aggregators in stats_store. The panel
emits nothing and (apart from export) has no writes.

request_id-based request tracing degrades to session-level grouping when request_id
has not been emitted yet (cross-domain follow-up). ⏳ fields surface as placeholders
until observability emits them. Never imports the agent loop.

Auth: viewer + admin may read; per-user detail is masked for viewer when the deploy
flag MASK_PER_USER_FOR_VIEWER is on.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response

from fleetent import agent_store, audit_log, auth, observability, user_store
from fleetent.platform.agent_statistics import stats_store
from fleetent.platform.model_provider_management import provider_admin_store

router = APIRouter(prefix="/admin/stats")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}
MASK_PER_USER_FOR_VIEWER = True
_DEFAULT_TRACE_LIMIT = 1000
_RUN_EVENT_TYPES = {"agent_run_completed", "agent_run_failed"}
_WINDOWS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


# --- injectable seams (observability / agent_store / model-provider / scheduling) ---


def fetch_traces(
    agent_id: str | None = None,
    user_id: str | None = None,
    channel: str | None = None,
    window: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch trace records from observability and flatten them for stats_store."""
    del channel
    start_ts, end_ts = _window_bounds(window)
    events = observability.query_trace_events(
        observability.TraceQuery(
            user_id=user_id,
            agent_name=agent_id,
            start_ts=start_ts,
            end_ts=end_ts,
            limit=_DEFAULT_TRACE_LIMIT,
        )
    )
    return [_trace_row(event) for event in events]


def fetch_approvals(agent_id: str | None = None) -> list[dict[str, Any]]:
    """Fetch approval decisions from observability permission_resolved events."""
    events = observability.query_trace_events(
        observability.TraceQuery(
            agent_name=agent_id,
            event_type="permission_resolved",
            limit=_DEFAULT_TRACE_LIMIT,
        )
    )
    return [
        {
            "decision": event.payload.get("decision"),
            "user_id": event.user_id,
            "session_id": event.session_id,
            "ts": event.ts.isoformat() if event.ts else None,
        }
        for event in events
    ]


def agent_allowed_tools(agent_id: str) -> list[str]:
    """The agent's allowed_tools allowlist (bridges agent_store)."""
    agent = agent_store.get_by_name(agent_id)
    return [] if agent is None else agent.allowed_tools


def pricing_table() -> dict[str, Any] | None:
    """Per-model pricing from model-provider."""
    return {
        str(provider["model"]): {
            "input": provider.get("input_price_per_1k"),
            "output": provider.get("output_price_per_1k"),
        }
        for provider in provider_admin_store.list_providers()
        if provider.get("model")
    }


def _window_bounds(window: str | None) -> tuple[datetime | None, datetime | None]:
    if window is None:
        return None, None
    now = datetime.now(UTC)
    return now - _WINDOWS.get(window, _WINDOWS["7d"]), now


def _trace_row(event: observability.TraceEvent) -> dict[str, Any]:
    payload = dict(event.payload)
    tokens = payload.get("tokens")
    if isinstance(tokens, dict):
        payload.setdefault("prompt_tokens", int(tokens.get("prompt", 0) or 0))
        payload.setdefault("completion_tokens", int(tokens.get("completion", 0) or 0))
        payload.setdefault("total_tokens", int(tokens.get("total", 0) or 0))
    payload.setdefault("agent_id", event.agent_name)
    payload.setdefault("agent_name", event.agent_name)
    payload.setdefault("user_id", event.user_id)
    payload.setdefault("session_id", event.session_id)
    payload.setdefault("event_type", event.event_type)
    payload.setdefault("run_id", event.run_id)
    payload.setdefault("ts", event.ts.isoformat() if event.ts else None)
    return payload


def _run_traces(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        trace
        for trace in traces
        if trace.get("event_type") in _RUN_EVENT_TYPES or trace.get("event_type") is None
    ]


# --- auth helpers -------------------------------------------------------------


def _current_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = auth.validate_session(authorization.split(" ", 1)[1], IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    if not auth.has_role(user, {"viewer", *_ADMIN_ROLES}):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _is_admin(user: user_store.User) -> bool:
    return auth.has_role(user, _ADMIN_ROLES)


# --- aggregated views ---------------------------------------------------------


@router.get("/agents/{agent_id}/overview")
def overview(
    agent_id: str, window: str = "7d", authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    traces = fetch_traces(agent_id=agent_id, window=window)
    run_traces = _run_traces(traces)
    return {
        "agent_id": agent_id,
        "usage": stats_store.aggregate_usage(run_traces),
        "performance": stats_store.aggregate_performance(run_traces),
        "approvals": stats_store.approval_stats(fetch_approvals(agent_id)),
        "cost": stats_store.cost(run_traces, pricing_table()),
    }


@router.get("/compare")
def compare(
    agents: str, key: str = "calls", authorization: str | None = Header(None)
) -> list[dict[str, Any]]:
    _current_user(authorization)
    metrics: dict[str, dict[str, Any]] = {}
    for agent_id in [a for a in agents.split(",") if a]:
        metrics[agent_id] = stats_store.aggregate_usage(
            _run_traces(fetch_traces(agent_id=agent_id))
        )
    return stats_store.compare_agents(metrics, key)


@router.get("/agents/{agent_id}/tools")
def tools(agent_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    traces = _run_traces(fetch_traces(agent_id=agent_id))
    return {
        "top_tools": stats_store.top_tools(traces),
        "coverage": stats_store.allowed_tools_coverage(traces, agent_allowed_tools(agent_id)),
    }


@router.get("/per-user")
def per_user(
    agent_id: str | None = None,
    sort_by: str = "total_tokens",
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    user = _current_user(authorization)
    ranking = stats_store.per_user_ranking(
        _run_traces(fetch_traces(agent_id=agent_id)),
        sort_by=sort_by,
    )
    if MASK_PER_USER_FOR_VIEWER and not _is_admin(user):
        for row in ranking:
            row["user_id"] = "***"
    return ranking


# --- request-level tracing ----------------------------------------------------


@router.get("/users/{user_id}/requests")
def user_requests(user_id: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return stats_store.build_request_list(_run_traces(fetch_traces(user_id=user_id)), user_id)


@router.get("/requests/{request_id}")
def request_trace(request_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    traces = fetch_traces()
    stream = stats_store.build_event_stream(traces, request_id)
    return stats_store.expand_subagents(stream, traces)


@router.get("/sessions/{session_id}/trace")
def degraded_trace(
    session_id: str, user_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    traces = fetch_traces(user_id=user_id)
    stream = stats_store.build_event_stream_degraded(traces, session_id, user_id)
    return stats_store.expand_subagents(stream, traces)


# --- export / scheduled report ------------------------------------------------


def _export_rows(view: str, agent_id: str | None) -> list[dict[str, Any]]:
    if view == "per-user":
        return stats_store.per_user_ranking(_run_traces(fetch_traces(agent_id=agent_id)))
    if view == "tools":
        traces = _run_traces(fetch_traces(agent_id=agent_id))
        return [{"tool": name, "calls": n} for name, n in stats_store.top_tools(traces)["top"]]
    # default: flat usage summary as a single row
    return [stats_store.aggregate_usage(_run_traces(fetch_traces(agent_id=agent_id)))]


@router.post("/export")
def export(
    view: str = "per-user",
    agent_id: str | None = None,
    authorization: str | None = Header(None),
) -> Response:
    user = _current_user(authorization)
    csv_text = stats_store.rows_to_csv(_export_rows(view, agent_id))
    audit_log.write_audit(user.id, "stats_export", "stats", agent_id, detail={"view": view})
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="stats-{view}.csv"'},
    )
