"""Persistence for resource monitoring + alerting (db runtime, named params, no ORM).

Lightweight self-hosted time-series (metric_samples) + alert rules / alerts /
maintenance windows. Schema owned by migration 016. Channel credentials are never
stored here. Retention cleanup is purge_before().
"""

import datetime
import json
import uuid
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_SEVERITIES = {"warning", "critical"}


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


# --- time series --------------------------------------------------------------


def record_sample(metric: str, target: str, value: float, ts: str | None = None) -> None:
    with _database().transaction() as conn:
        conn.execute(
            "INSERT INTO metric_samples (metric, target, value, ts) "
            "VALUES (:metric, :target, :value, :ts)",
            {"metric": metric, "target": target, "value": value, "ts": ts or _now()},
        )


def query_samples(metric: str, target: str, since: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT value, ts FROM metric_samples WHERE metric = :metric AND target = :target"
    params: dict[str, Any] = {"metric": metric, "target": target}
    if since:
        sql += " AND ts >= :since"
        params["since"] = since
    return _database().execute(sql + " ORDER BY ts", params).fetchall()


def purge_before(ts: str) -> int:
    with _database().transaction() as conn:
        result = conn.execute("DELETE FROM metric_samples WHERE ts < :ts", {"ts": ts})
        return result.rowcount


# --- alert rules --------------------------------------------------------------


def create_rule(
    metric: str,
    comparator: str,
    threshold: float,
    *,
    target: str | None = None,
    for_seconds: int = 0,
    severity: str = "warning",
    channels: list[str] | None = None,
    rule_id: str | None = None,
) -> str:
    if severity not in _SEVERITIES:
        raise ValueError(f"severity must be one of {_SEVERITIES}")
    rid = rule_id or uuid.uuid4().hex[:12]
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO alert_rules
                (id, metric, target, comparator, threshold, for_seconds, severity,
                 enabled, channels, created_at, updated_at)
            VALUES (:id, :metric, :target, :comparator, :threshold, :for_seconds, :severity,
                    1, :channels, :created_at, :updated_at)
            """,
            {
                "id": rid,
                "metric": metric,
                "target": target,
                "comparator": comparator,
                "threshold": threshold,
                "for_seconds": for_seconds,
                "severity": severity,
                "channels": json.dumps(channels or []),
                "created_at": now,
                "updated_at": now,
            },
        )
    return rid


def get_rule(rule_id: str) -> dict[str, Any] | None:
    row = (
        _database().execute("SELECT * FROM alert_rules WHERE id = :id", {"id": rule_id}).fetchone()
    )
    return _decode_rule(row) if row else None


def list_rules(enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM alert_rules"
    if enabled_only:
        sql += " WHERE enabled = 1"
    return [_decode_rule(r) for r in _database().execute(sql + " ORDER BY id").fetchall()]


def set_rule_enabled(rule_id: str, enabled: bool) -> None:
    with _database().transaction() as conn:
        conn.execute(
            "UPDATE alert_rules SET enabled = :en, updated_at = :now WHERE id = :id",
            {"en": 1 if enabled else 0, "now": _now(), "id": rule_id},
        )


def delete_rule(rule_id: str) -> None:
    with _database().transaction() as conn:
        conn.execute("DELETE FROM alert_rules WHERE id = :id", {"id": rule_id})


def _decode_rule(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["channels"] = json.loads(out["channels"]) if out.get("channels") else []
    return out


# --- alerts -------------------------------------------------------------------


def find_active_alert(rule_id: str, target: str | None) -> dict[str, Any] | None:
    """Return a non-resolved alert for (rule, target) — drives dedup."""
    row = (
        _database()
        .execute(
            "SELECT * FROM alerts WHERE rule_id = :rid AND target IS :target "
            "AND status != 'resolved' LIMIT 1",
            {"rid": rule_id, "target": target},
        )
        .fetchone()
    )
    return dict(row) if row else None


def create_alert(
    rule_id: str, target: str | None, severity: str, snapshot: dict[str, Any] | None
) -> str:
    aid = uuid.uuid4().hex[:12]
    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO alerts
                (id, rule_id, target, severity, status, fired_at, snapshot, updated_at)
            VALUES (:id, :rule_id, :target, :severity, 'firing', :fired_at, :snapshot, :updated_at)
            """,
            {
                "id": aid,
                "rule_id": rule_id,
                "target": target,
                "severity": severity,
                "fired_at": now,
                "snapshot": json.dumps(snapshot) if snapshot else None,
                "updated_at": now,
            },
        )
    return aid


def set_alert_status(alert_id: str, status: str, **extra: Any) -> None:
    fields = {"status": status, "updated_at": _now(), **extra}
    if status == "resolved":
        fields["resolved_at"] = _now()
    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    with _database().transaction() as conn:
        conn.execute(f"UPDATE alerts SET {assignments} WHERE id = :id", {**fields, "id": alert_id})


def get_alert(alert_id: str) -> dict[str, Any] | None:
    row = _database().execute("SELECT * FROM alerts WHERE id = :id", {"id": alert_id}).fetchone()
    return dict(row) if row else None


def list_alerts(
    status: str | None = None, severity: str | None = None, target: str | None = None
) -> list[dict[str, Any]]:
    clauses, params = [], {}
    for col, val in (("status", status), ("severity", severity), ("target", target)):
        if val:
            clauses.append(f"{col} = :{col}")
            params[col] = val
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return (
        _database()
        .execute(f"SELECT * FROM alerts{where} ORDER BY fired_at DESC", params)
        .fetchall()
    )


# --- maintenance windows ------------------------------------------------------


def add_window(target: str | None, start_ts: str, end_ts: str) -> str:
    wid = uuid.uuid4().hex[:12]
    with _database().transaction() as conn:
        conn.execute(
            "INSERT INTO maintenance_windows (id, target, start_ts, end_ts, created_at) "
            "VALUES (:id, :target, :start_ts, :end_ts, :now)",
            {"id": wid, "target": target, "start_ts": start_ts, "end_ts": end_ts, "now": _now()},
        )
    return wid


def list_windows() -> list[dict[str, Any]]:
    return _database().execute("SELECT * FROM maintenance_windows ORDER BY start_ts").fetchall()
