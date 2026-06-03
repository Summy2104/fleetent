"""FastAPI router for /admin/stats — the Agent statistics panel (read-only).

An aggregation layer over observability traces / approvals / agent_store. It fetches
data through injectable seams and runs the pure aggregators in stats_store. The panel
emits nothing and (apart from export / scheduled-report config) has no writes.

request_id-based request tracing degrades to session-level grouping when request_id
has not been emitted yet (cross-domain follow-up). ⏳ fields surface as placeholders
until observability emits them. Never imports the agent loop.

Auth: viewer + admin may read; per-user detail is masked for viewer when the deploy
flag MASK_PER_USER_FOR_VIEWER is on.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel

from fleetent import auth, schedule_store, user_store
from fleetent.governance import audit_log
from fleetent.platform.agent_statistics import stats_store

router = APIRouter(prefix="/admin/stats")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}
MASK_PER_USER_FOR_VIEWER = True


# --- injectable seams (observability / agent_store / model-provider / scheduling) ---


def fetch_traces(
    agent_id: str | None = None,
    user_id: str | None = None,
    channel: str | None = None,
    window: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch trace records (observability follow-up). Placeholder returns none."""
    return []


def fetch_approvals(agent_id: str | None = None) -> list[dict[str, Any]]:
    """Fetch permission_gate approval records (placeholder)."""
    return []


def agent_allowed_tools(agent_id: str) -> list[str]:
    """The agent's allowed_tools allowlist (bridges agent_store)."""
    return []


def pricing_table() -> dict[str, Any] | None:
    """Per-model pricing from model-provider. None => table not online yet."""
    return None


# period -> cron: weekly = Monday 09:00, monthly = 1st of month 09:00.
_PERIOD_CRON = {"weekly": "0 9 * * 1", "monthly": "0 9 1 * *"}
_REPORT_TIMEZONE = "UTC"


def schedule_report(period: str, agent_id: str, recipient: str, user_id: str) -> str:
    """Register a recurring stats email report via schedule_store. Returns task id.

    The recurring job is a normal scheduled task whose message carries the report
    directive; the email sender is wired by the scheduling runtime (mocked in tests).
    """
    task = schedule_store.create(
        name=f"stats-report:{agent_id}:{period}",
        cron_expr=_PERIOD_CRON[period],
        timezone=_REPORT_TIMEZONE,
        user_id=user_id,
        agent_name=agent_id,
        message=f"__stats_report__ period={period} recipient={recipient}",
        source="stats_report",
    )
    return str(task["id"])


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


class ReportBody(BaseModel):
    period: str  # "weekly" | "monthly"
    agent_id: str
    recipient: str


# --- aggregated views ---------------------------------------------------------


@router.get("/agents/{agent_id}/overview")
def overview(
    agent_id: str, window: str = "7d", authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    traces = fetch_traces(agent_id=agent_id, window=window)
    return {
        "agent_id": agent_id,
        "usage": stats_store.aggregate_usage(traces),
        "performance": stats_store.aggregate_performance(traces),
        "approvals": stats_store.approval_stats(fetch_approvals(agent_id)),
        "cost": stats_store.cost(traces, pricing_table()),
    }


@router.get("/compare")
def compare(
    agents: str, key: str = "calls", authorization: str | None = Header(None)
) -> list[dict[str, Any]]:
    _current_user(authorization)
    metrics: dict[str, dict[str, Any]] = {}
    for agent_id in [a for a in agents.split(",") if a]:
        metrics[agent_id] = stats_store.aggregate_usage(fetch_traces(agent_id=agent_id))
    return stats_store.compare_agents(metrics, key)


@router.get("/agents/{agent_id}/tools")
def tools(agent_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    traces = fetch_traces(agent_id=agent_id)
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
    ranking = stats_store.per_user_ranking(fetch_traces(agent_id=agent_id), sort_by=sort_by)
    if MASK_PER_USER_FOR_VIEWER and not _is_admin(user):
        for row in ranking:
            row["user_id"] = "***"
    return ranking


# --- request-level tracing ----------------------------------------------------


@router.get("/users/{user_id}/requests")
def user_requests(user_id: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return stats_store.build_request_list(fetch_traces(user_id=user_id), user_id)


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
        return stats_store.per_user_ranking(fetch_traces(agent_id=agent_id))
    if view == "tools":
        traces = fetch_traces(agent_id=agent_id)
        return [{"tool": name, "calls": n} for name, n in stats_store.top_tools(traces)["top"]]
    # default: flat usage summary as a single row
    return [stats_store.aggregate_usage(fetch_traces(agent_id=agent_id))]


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


@router.post("/reports")
def configure_report(body: ReportBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _current_user(authorization)
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="admin required")
    if body.period not in {"weekly", "monthly"}:
        raise HTTPException(status_code=422, detail="period must be weekly or monthly")
    task_id = schedule_report(body.period, body.agent_id, body.recipient, user.id)
    audit_log.write_audit(
        user.id,
        "stats_report_config",
        "stats",
        body.agent_id,
        detail={"period": body.period, "task_id": task_id},
    )
    return {"task_id": task_id, "period": body.period}
