"""FastAPI router for /admin/monitoring + /admin/alerts — resource monitoring & alerting.

Owns the management behaviour: time-series dashboards, alert-rule CRUD, the alert
center (list/detail/ack/silence/assign), maintenance windows, and multi-channel
notification dispatch with retry. Threshold×duration evaluation / suppression /
escalation logic lives in alerting.py; collection sources (host/proc/container/infra)
and IM delivery are reached through injectable seams. Channel credentials are never
returned plaintext — masking is applied in the serialization layer. No agent loop import.

Auth: viewer reads dashboards + alert history; admin manages rules / ack / silence /
channels / maintenance.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import audit_log, auth, monitoring_store, user_store

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}
_SENSITIVE = ("password", "secret", "token", "api_key")
NOTIFY_MAX_RETRIES = 3


# --- injectable channel seams (no real email/IM/webhook in tests) -------------


def send_email(recipient: str, subject: str, body: str) -> None:
    """Send an alert email (SMTP). Placeholder; monkeypatched in tests."""
    raise RuntimeError("email channel not configured")


def send_im(target: str, text: str) -> None:
    """Push an alert to admins via im-gateway. Placeholder."""
    raise RuntimeError("im channel not configured")


def send_webhook(url: str, payload: dict[str, Any]) -> None:
    """POST an alert to an external on-call webhook. Placeholder."""
    raise RuntimeError("webhook channel not configured")


# --- masking ------------------------------------------------------------------


def _mask(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (
                "****"
                if isinstance(k, str) and any(s in k.lower() for s in _SENSITIVE) and v
                else _mask(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_mask(v) for v in value]
    return value


# --- notification dispatch (retry + failure record) ---------------------------


def dispatch_notification(
    alert: dict[str, Any], channels: list[str], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Send an alert over each configured channel with bounded retry. in_app always
    succeeds (it writes to the alert center). Returns sent / failed channel lists."""
    config = config or {}
    sent, failed = [], []
    for channel in channels:
        ok = False
        last_error = None
        for _ in range(NOTIFY_MAX_RETRIES):
            try:
                if channel == "email":
                    send_email(config.get("recipient", "admin@local"), "alert", str(alert))
                elif channel == "im":
                    send_im(config.get("im_target", "admins"), str(alert))
                elif channel == "webhook":
                    send_webhook(config.get("webhook_url", ""), alert)
                elif channel == "in_app":
                    pass  # recorded in the alert center; never fails
                ok = True
                break
            except Exception as exc:  # noqa: BLE001 — record + continue to next channel
                last_error = str(exc)
        (sent if ok else failed).append(
            channel if ok else {"channel": channel, "error": last_error}
        )
    return {"sent": sent, "failed": failed}


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


def _require_admin(authorization: str | None) -> user_store.User:
    user = _current_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


# --- request bodies -----------------------------------------------------------


class RuleBody(BaseModel):
    metric: str
    comparator: str
    threshold: float
    target: str | None = None
    for_seconds: int = 0
    severity: str = "warning"
    channels: list[str] | None = None


class AckBody(BaseModel):
    assignee: str | None = None


class WindowBody(BaseModel):
    target: str | None = None
    start_ts: str
    end_ts: str


# --- monitoring dashboards ----------------------------------------------------


@router.get("/monitoring/metrics")
def metrics(
    metric: str, target: str, since: str | None = None, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    samples = monitoring_store.query_samples(metric, target, since=since)
    return {
        "metric": metric,
        "target": target,
        "samples": samples,
        "latest": samples[-1]["value"] if samples else None,
    }


# --- alert rules --------------------------------------------------------------


@router.get("/alerts/rules")
def list_rules(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return [_mask(r) for r in monitoring_store.list_rules()]


@router.post("/alerts/rules")
def create_rule(body: RuleBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if body.severity not in {"warning", "critical"}:
        raise HTTPException(status_code=422, detail="severity must be warning or critical")
    rid = monitoring_store.create_rule(
        body.metric,
        body.comparator,
        body.threshold,
        target=body.target,
        for_seconds=body.for_seconds,
        severity=body.severity,
        channels=body.channels,
    )
    audit_log.write_audit(user.id, "alert.rule_create", "alert_rule", rid)
    return {"id": rid}


@router.post("/alerts/rules/{rule_id}/disable")
def disable_rule(rule_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    monitoring_store.set_rule_enabled(rule_id, False)
    audit_log.write_audit(user.id, "alert.rule_disable", "alert_rule", rule_id)
    return {"id": rule_id, "enabled": False}


@router.delete("/alerts/rules/{rule_id}")
def delete_rule(rule_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    monitoring_store.delete_rule(rule_id)
    audit_log.write_audit(user.id, "alert.rule_delete", "alert_rule", rule_id)
    return {"id": rule_id, "deleted": True}


# --- alert center -------------------------------------------------------------


@router.get("/alerts")
def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    target: str | None = None,
    authorization: str | None = Header(None),
) -> list[dict[str, Any]]:
    _current_user(authorization)
    return [
        _mask(a)
        for a in monitoring_store.list_alerts(status=status, severity=severity, target=target)
    ]


@router.post("/alerts/{alert_id}/ack")
def ack_alert(
    alert_id: str, body: AckBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if monitoring_store.get_alert(alert_id) is None:
        raise HTTPException(status_code=404, detail="alert not found")
    monitoring_store.set_alert_status(alert_id, "ack", acked_by=user.id, assignee=body.assignee)
    audit_log.write_audit(
        user.id, "alert.ack", "alert", alert_id, detail={"assignee": body.assignee}
    )
    return {"id": alert_id, "status": "ack"}


@router.post("/alerts/{alert_id}/silence")
def silence_alert(alert_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    monitoring_store.set_alert_status(alert_id, "silenced")
    audit_log.write_audit(user.id, "alert.silence", "alert", alert_id)
    return {"id": alert_id, "status": "silenced"}


@router.post("/alerts/maintenance")
def add_maintenance(body: WindowBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    wid = monitoring_store.add_window(body.target, body.start_ts, body.end_ts)
    audit_log.write_audit(user.id, "alert.maintenance_add", "maintenance_window", wid)
    return {"id": wid}
