"""Tests for monitoring_store (migration 016) + alerting pure logic. Scenarios 86-93."""

import datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent import alerting
from fleetent import monitoring_store as store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def store_db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def _ts(dt):
    return dt.isoformat()


# --- time series + retention (场景 86) ---------------------------------------


def test_record_and_query_samples(store_db):
    store.record_sample("cpu", "host:h1", 50.0, ts="2026-06-01T00:00:00")
    store.record_sample("cpu", "host:h1", 70.0, ts="2026-06-01T00:01:00")
    samples = store.query_samples("cpu", "host:h1")
    assert [s["value"] for s in samples] == [50.0, 70.0]


def test_query_since_and_purge(store_db):
    store.record_sample("cpu", "host:h1", 1.0, ts="2026-06-01T00:00:00")
    store.record_sample("cpu", "host:h1", 2.0, ts="2026-06-02T00:00:00")
    assert len(store.query_samples("cpu", "host:h1", since="2026-06-02T00:00:00")) == 1
    purged = store.purge_before("2026-06-02T00:00:00")
    assert purged == 1


# --- alert rules (场景 89 config) --------------------------------------------


def test_rule_crud_and_severity_validation(store_db):
    rid = store.create_rule(
        "cpu", ">", 85.0, for_seconds=300, severity="critical", channels=["email", "in_app"]
    )
    r = store.get_rule(rid)
    assert r["severity"] == "critical" and r["channels"] == ["email", "in_app"]
    with pytest.raises(ValueError):
        store.create_rule("cpu", ">", 85.0, severity="bogus")
    store.set_rule_enabled(rid, False)
    assert store.get_rule(rid)["enabled"] == 0


# --- alerts dedup + state (场景 91) ------------------------------------------


def test_alert_create_dedup_and_resolve(store_db):
    rid = store.create_rule("cpu", ">", 85.0)
    aid = store.create_alert(rid, "host:h1", "warning", {"value": 90})
    assert store.find_active_alert(rid, "host:h1") is not None  # dedup target
    store.set_alert_status(aid, "ack", acked_by="admin-1", assignee="ops")
    assert store.get_alert(aid)["acked_by"] == "admin-1"
    store.set_alert_status(aid, "resolved")
    assert store.get_alert(aid)["resolved_at"] is not None
    assert store.find_active_alert(rid, "host:h1") is None  # resolved excluded


def test_maintenance_window(store_db):
    store.add_window("host:h1", "2026-06-01T00:00:00", "2026-06-01T02:00:00")
    assert len(store.list_windows()) == 1


# --- alerting pure logic ------------------------------------------------------


def test_evaluate_sustained_fires_spike_does_not():
    now = datetime.datetime(2026, 6, 1, 0, 10, 0)
    rule = {"comparator": ">", "threshold": 85, "for_seconds": 300, "enabled": 1}
    # sustained: samples spanning >5min all above 85
    sustained = [
        {"value": 90, "ts": _ts(now - datetime.timedelta(seconds=360))},
        {"value": 92, "ts": _ts(now - datetime.timedelta(seconds=120))},
        {"value": 91, "ts": _ts(now)},
    ]
    assert alerting.evaluate(rule, sustained, now) is True
    # spike: only the latest sample breaches
    spike = [
        {"value": 10, "ts": _ts(now - datetime.timedelta(seconds=360))},
        {"value": 95, "ts": _ts(now)},
    ]
    assert alerting.evaluate(rule, spike, now) is False


def test_evaluate_disabled_rule():
    now = datetime.datetime(2026, 6, 1, 0, 0, 0)
    rule = {"comparator": ">", "threshold": 1, "for_seconds": 0, "enabled": 0}
    assert alerting.evaluate(rule, [{"value": 99, "ts": _ts(now)}], now) is False


def test_in_maintenance():
    now = datetime.datetime(2026, 6, 1, 1, 0, 0)
    windows = [
        {"target": "host:h1", "start_ts": "2026-06-01T00:00:00", "end_ts": "2026-06-01T02:00:00"}
    ]
    assert alerting.in_maintenance(windows, "host:h1", now) is True
    assert alerting.in_maintenance(windows, "host:h2", now) is False


def test_suppression_host_down_suppresses_container():  # 场景 92
    down = {"host:h1"}
    assert alerting.is_suppressed("host:h1/container:c1", down) is True
    assert alerting.is_suppressed("host:h1", down) is False  # the host alert itself
    assert alerting.is_suppressed("host:h2/container:c1", down) is False


def test_should_escalate():  # 场景 90
    now = datetime.datetime(2026, 6, 1, 0, 10, 0)
    alert = {
        "severity": "critical",
        "status": "notified",
        "fired_at": _ts(now - datetime.timedelta(seconds=600)),
    }
    assert alerting.should_escalate(alert, now, 300) is True
    warn = {**alert, "severity": "warning"}
    assert alerting.should_escalate(warn, now, 300) is False
    acked = {**alert, "status": "ack"}
    assert alerting.should_escalate(acked, now, 300) is False
