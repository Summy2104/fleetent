"""Tests for monitor_admin_api (/admin/monitoring, /admin/alerts). Scenarios 86-96."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.audit_log as audit
import fleetent.auth as auth
import fleetent.platform.resource_monitoring.monitor_admin_api as api
import fleetent.platform.resource_monitoring.monitoring_store as store
import fleetent.user_store as user_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    user_store._init_db()
    audit._init_db()
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


# --- dashboards (场景 86/87/88) ----------------------------------------------


def test_metrics_dashboard(client):
    store.record_sample("sandbox_oom", "host:h1", 2.0, ts="2026-06-01T00:00:00")
    token, _ = _session_for("viewer")
    r = client.get(
        "/admin/monitoring/metrics?metric=sandbox_oom&target=host:h1", headers=_hdr(token)
    )
    assert r.json()["latest"] == 2.0


def test_metrics_requires_auth(client):
    assert client.get("/admin/monitoring/metrics?metric=cpu&target=h").status_code == 401


# --- rule CRUD (场景 89/95) ---------------------------------------------------


def test_create_rule_admin_only(client):
    viewer, _ = _session_for("viewer")
    assert (
        client.post(
            "/admin/alerts/rules",
            headers=_hdr(viewer),
            json={"metric": "cpu", "comparator": ">", "threshold": 85},
        ).status_code
        == 403
    )
    admin, _ = _session_for("admin")
    r = client.post(
        "/admin/alerts/rules",
        headers=_hdr(admin),
        json={
            "metric": "cpu",
            "comparator": ">",
            "threshold": 85,
            "for_seconds": 300,
            "severity": "critical",
            "channels": ["email"],
        },
    )
    assert r.status_code == 200
    assert any(a["action"] == "alert.rule_create" for a in audit.search_audit())


def test_create_rule_bad_severity_422(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/alerts/rules",
        headers=_hdr(token),
        json={"metric": "cpu", "comparator": ">", "threshold": 1, "severity": "x"},
    )
    assert r.status_code == 422


# --- alert center ack/silence (场景 91/95) -----------------------------------


def test_ack_alert(client):
    rid = store.create_rule("cpu", ">", 85.0, severity="critical")
    aid = store.create_alert(rid, "host:h1", "critical", {"value": 90})
    token, _ = _session_for("admin")
    r = client.post(f"/admin/alerts/{aid}/ack", headers=_hdr(token), json={"assignee": "ops"})
    assert r.status_code == 200
    assert store.get_alert(aid)["acked_by"] is not None
    assert store.get_alert(aid)["assignee"] == "ops"
    assert any(a["action"] == "alert.ack" for a in audit.search_audit())


def test_viewer_cannot_ack(client):
    rid = store.create_rule("cpu", ">", 85.0)
    aid = store.create_alert(rid, "host:h1", "warning", None)
    token, _ = _session_for("viewer")
    assert client.post(f"/admin/alerts/{aid}/ack", headers=_hdr(token), json={}).status_code == 403


def test_list_alerts_filter(client):
    rid = store.create_rule("cpu", ">", 85.0)
    store.create_alert(rid, "host:h1", "critical", None)
    token, _ = _session_for("viewer")
    r = client.get("/admin/alerts?severity=critical", headers=_hdr(token))
    assert len(r.json()) == 1


def test_maintenance_window_admin(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/alerts/maintenance",
        headers=_hdr(token),
        json={
            "target": "host:h1",
            "start_ts": "2026-06-01T00:00:00",
            "end_ts": "2026-06-01T02:00:00",
        },
    )
    assert r.status_code == 200


# --- notification dispatch: channels, retry, webhook, masking (场景 89/94/96) -


def test_dispatch_email_and_in_app(monkeypatch):
    sent_mail = []
    monkeypatch.setattr(api, "send_email", lambda to, s, b: sent_mail.append(to))
    out = api.dispatch_notification({"id": "a1"}, ["email", "in_app"], {"recipient": "ops@x.com"})
    assert "email" in out["sent"] and "in_app" in out["sent"]
    assert sent_mail == ["ops@x.com"]


def test_dispatch_webhook(monkeypatch):  # 场景 94
    posted = []
    monkeypatch.setattr(api, "send_webhook", lambda url, payload: posted.append((url, payload)))
    out = api.dispatch_notification({"id": "a1"}, ["webhook"], {"webhook_url": "https://oncall"})
    assert out["sent"] == ["webhook"]
    assert posted[0][0] == "https://oncall"


def test_dispatch_retries_then_records_failure(monkeypatch):
    attempts = {"n": 0}

    def flaky(*a):
        attempts["n"] += 1
        raise RuntimeError("smtp down")

    monkeypatch.setattr(api, "send_email", flaky)
    out = api.dispatch_notification({"id": "a1"}, ["email"], {})
    assert attempts["n"] == api.NOTIFY_MAX_RETRIES  # retried
    assert out["failed"][0]["channel"] == "email"
    assert "smtp down" in out["failed"][0]["error"]


def test_default_path_makes_no_network_calls(client):  # 场景 96
    # Listing/dashboards never invoke channels; only explicit dispatch does.
    store.record_sample("cpu", "host:h1", 10.0)
    token, _ = _session_for("admin")
    # send_* seams are the unconfigured placeholders that raise — none should be hit here
    assert (
        client.get(
            "/admin/monitoring/metrics?metric=cpu&target=host:h1", headers=_hdr(token)
        ).status_code
        == 200
    )
    assert client.get("/admin/alerts", headers=_hdr(token)).status_code == 200


def test_rule_list_masks_secrets(client, monkeypatch):
    token, _ = _session_for("admin")
    # a rule with a channel config carrying a secret would be masked on output
    masked = api._mask({"webhook_secret": "shhh", "url": "https://x", "nested": {"token": "t"}})
    assert masked["webhook_secret"] == "****"
    assert masked["nested"]["token"] == "****"
    assert masked["url"] == "https://x"


# --- escalation runtime (场景 90, tasks 6.3/6.4) ------------------------------


def test_escalate_pending_promotes_unacked_critical_and_audits(client, monkeypatch):
    # a critical alert fired long ago and never acked
    aid = store.create_alert("rule-1", "host:h1", "critical", {"value": 99})
    store.set_alert_status(aid, "notified", fired_at="2026-06-01T00:00:00+00:00")

    dispatched = []
    monkeypatch.setattr(
        api,
        "dispatch_notification",
        lambda alert, channels, config=None: (
            dispatched.append(channels) or {"sent": channels, "failed": []}
        ),
    )

    import datetime

    now = datetime.datetime(2026, 6, 1, 0, 30, tzinfo=datetime.UTC)
    result = api.escalate_pending(
        now=now, escalate_after_seconds=600, escalation_channels=["im", "webhook"]
    )

    assert aid in result["escalated"]
    assert store.get_alert(aid)["status"] == "escalated"
    assert dispatched == [["im", "webhook"]]  # promoted to higher channels
    assert any(row["action"] == "alert.escalate" for row in audit.search_audit())


def test_escalate_pending_skips_recent_or_acked(client, monkeypatch):
    fresh = store.create_alert("rule-1", "host:h2", "critical", {})  # just fired
    acked = store.create_alert("rule-1", "host:h3", "critical", {})
    store.set_alert_status(acked, "ack", fired_at="2026-06-01T00:00:00+00:00")

    monkeypatch.setattr(api, "dispatch_notification", lambda *a, **k: {"sent": [], "failed": []})
    import datetime

    now = datetime.datetime(2026, 6, 1, 0, 30, tzinfo=datetime.UTC)
    result = api.escalate_pending(now=now, escalate_after_seconds=600, escalation_channels=["im"])

    assert fresh not in result["escalated"]  # too recent
    assert acked not in result["escalated"]  # already acked
