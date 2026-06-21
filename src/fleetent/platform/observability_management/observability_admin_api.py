"""FastAPI router for /admin/observability query endpoints."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from fleetent import auth, observability, user_store

router = APIRouter(prefix="/admin/observability")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}


def _require_admin(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    token = authorization.split(" ", 1)[1]
    user_id = auth.validate_session(token, IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


@router.get("/traces")
def traces(
    run_id: str | None = None,
    user_id: str | None = None,
    agent: str | None = None,
    session_id: str | None = None,
    tenant_id: str | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _require_admin(authorization)
    events = observability.query_trace_events(
        observability.TraceQuery(
            run_id=run_id,
            user_id=user_id,
            agent_name=agent,
            session_id=session_id,
            tenant_id=tenant_id,
            event_type=event_type,
            start_ts=since,
            end_ts=until,
            limit=limit,
        )
    )
    return [asdict(event) for event in events]


@router.get("/usage")
def usage(
    user_id: str | None = None,
    agent: str | None = None,
    session_id: str | None = None,
    tenant_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 10_000,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _require_admin(authorization)
    summary = observability.get_usage_summary(
        observability.UsageQuery(
            user_id=user_id,
            agent_name=agent,
            session_id=session_id,
            tenant_id=tenant_id,
            start_ts=since,
            end_ts=until,
            limit=limit,
        )
    )
    return asdict(summary)


@router.get("/performance")
def performance(
    user_id: str | None = None,
    agent: str | None = None,
    session_id: str | None = None,
    tenant_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 10_000,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    _require_admin(authorization)
    summary = observability.get_performance_summary(
        observability.PerformanceQuery(
            user_id=user_id,
            agent_name=agent,
            session_id=session_id,
            tenant_id=tenant_id,
            start_ts=since,
            end_ts=until,
            limit=limit,
        )
    )
    return asdict(summary)
