"""Tests for the four-layer collectors + collection-failure self-alert (tasks 2.x).

All collection sources (host / process / container / infra) are monkeypatched, so the
default run path touches no real /proc, docker, PostgreSQL, Redis, etc. The orchestrator
writes samples through monitoring_store and, on a per-layer failure, marks the layer
"采集中断" (collection_status=0) and raises a built-in alert instead of silently dropping.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from fleetent.platform.resource_monitoring import collectors
from fleetent.platform.resource_monitoring import monitoring_store as store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def _stub_layers(monkeypatch):
    monkeypatch.setattr(collectors, "collect_host", lambda: [("cpu", "host:h1", 12.0)])
    monkeypatch.setattr(collectors, "collect_process", lambda: [("rss_mb", "process:self", 99.0)])
    monkeypatch.setattr(
        collectors,
        "collect_containers",
        lambda: [
            ("oom_kills", "container:pool", 2.0),
            ("timeout_kills", "container:pool", 1.0),
            ("active", "container:pool", 5.0),
        ],
    )
    monkeypatch.setattr(collectors, "collect_infra", lambda: [("up", "infra:redis", 1.0)])


# --- happy path: all four layers write samples (场景 86/87 data plane) ---------


def test_collect_once_records_all_layers(db, monkeypatch):
    _stub_layers(monkeypatch)
    collectors.collect_once()

    assert store.query_samples("cpu", "host:h1")[-1]["value"] == 12.0
    assert store.query_samples("rss_mb", "process:self")[-1]["value"] == 99.0
    assert store.query_samples("oom_kills", "container:pool")[-1]["value"] == 2.0
    assert store.query_samples("timeout_kills", "container:pool")[-1]["value"] == 1.0
    assert store.query_samples("active", "container:pool")[-1]["value"] == 5.0
    assert store.query_samples("up", "infra:redis")[-1]["value"] == 1.0
    # every layer marked healthy
    for layer in ("host", "process", "container", "infra"):
        assert store.query_samples("collection_status", f"layer:{layer}")[-1]["value"] == 1.0


# --- per-layer failure: mark 采集中断 + built-in alert, do not drop others -----


def test_layer_failure_marks_interrupted_and_alerts(db, monkeypatch):
    _stub_layers(monkeypatch)

    def boom():
        raise RuntimeError("redis unreachable")

    monkeypatch.setattr(collectors, "collect_infra", boom)
    summary = collectors.collect_once()

    # failed layer marked down, healthy layers still recorded (no silent total drop)
    assert store.query_samples("collection_status", "layer:infra")[-1]["value"] == 0.0
    assert store.query_samples("cpu", "host:h1")[-1]["value"] == 12.0
    assert summary["failed"] == ["infra"]

    # a built-in collection-failure alert was raised (not silent)
    alerts = store.list_alerts(target="layer:infra")
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "critical"
    assert alerts[0]["rule_id"] == collectors.COLLECTION_FAILURE_RULE


def test_repeated_failure_dedups_to_single_alert(db, monkeypatch):
    _stub_layers(monkeypatch)
    monkeypatch.setattr(
        collectors, "collect_infra", lambda: (_ for _ in ()).throw(RuntimeError("x"))
    )
    collectors.collect_once()
    collectors.collect_once()
    assert len(store.list_alerts(target="layer:infra")) == 1  # deduped


# --- interval / retention are injectable (task 2.3) ---------------------------


def test_retention_purge_uses_injectable_window(db, monkeypatch):
    seen = {}
    monkeypatch.setattr(store, "purge_before", lambda ts: seen.update(ts=ts) or 0)
    monkeypatch.setattr(collectors, "RETENTION_SECONDS", 3600)
    collectors.purge_expired(now="2026-06-02T10:00:00+00:00")
    assert seen["ts"] == "2026-06-02T09:00:00+00:00"  # now - retention
