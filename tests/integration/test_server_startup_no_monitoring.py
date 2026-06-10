"""Verify server starts cleanly after monitoring module removal.

- app lifespan completes without error
- GET /health returns 200
- Admin routes that existed before the change still respond (not 404)
- No monitoring_collect job is registered in the scheduler
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fleetent import server as srv
from fleetent import user_store as us
from fleetent.cron_scheduler import CronScheduler
from tests.integration._migration_template import apply_migrations


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    apply_migrations(tmp_path / "users.db")
    monkeypatch.chdir(tmp_path)
    with TestClient(srv.app) as c:
        yield c


def test_health_endpoint_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_admin_route_is_present(client):
    # /admin/me requires auth; 401/403 means the route exists (not 404)
    resp = client.get("/admin/me")
    assert resp.status_code != 404


def test_no_monitoring_collect_job_registered(tmp_path, monkeypatch):
    """monitoring_collect must not appear in the scheduler after startup."""
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    apply_migrations(tmp_path / "users.db")
    monkeypatch.chdir(tmp_path)

    original_add_interval = CronScheduler.add_interval_job
    captured_jobs: list[str] = []

    def _capture_add_interval(self, func, seconds, job_id):
        captured_jobs.append(job_id)
        return original_add_interval(self, func, seconds, job_id)

    monkeypatch.setattr(CronScheduler, "add_interval_job", _capture_add_interval)

    with TestClient(srv.app):
        pass

    assert "monitoring_collect" not in captured_jobs, (
        f"monitoring_collect was registered — jobs: {captured_jobs}"
    )
