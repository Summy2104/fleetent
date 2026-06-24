"""Tests for server lifespan wiring: MCP startup, adapter env detection, health."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integration._migration_template import apply_migrations

_OWNER_ROUTE = "/admin/im/" + "connectors"


@pytest.fixture(autouse=True)
def isolate_runtime_config_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@pytest.fixture()
def client(tmp_path, monkeypatch, isolated_schedule_db):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    return TestClient(app_module().app)


def app_module():
    import fleetent.server as srv

    return srv


def test_health_includes_adapter_status(tmp_path, monkeypatch, isolated_schedule_db):
    """Health endpoint returns adapter presence flags; both False when no tokens."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here — prevents Settings from loading tokens

    import fleetent.server as srv

    client = TestClient(srv.app)
    resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["adapters"]["slack"] is False
    assert data["adapters"]["telegram"] is False


def test_health_adapter_flags_true_when_connectors_present(
    tmp_path, monkeypatch, isolated_schedule_db
):
    """Health reflects per-agent Slack + Telegram presence."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")

    import fleetent.server as srv

    # Slack is per-agent (agent.yaml im.slack); Telegram is owner-level.
    monkeypatch.setattr(srv, "_slack_adapter_configured", lambda: True)
    monkeypatch.setattr(srv, "_telegram_adapter_configured", lambda: True)

    client = TestClient(srv.app)
    resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["adapters"]["slack"] is True
    assert data["adapters"]["telegram"] is True


def test_admin_im_router_removed(tmp_path, monkeypatch, isolated_schedule_db):
    """Owner-level IM connector routes are removed from the platform app."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    monkeypatch.chdir(tmp_path)

    import fleetent.server as srv

    client = TestClient(srv.app)
    resp = client.get(_OWNER_ROUTE)

    assert resp.status_code == 404


def test_lifespan_boots_when_approval_state_db_unwired(tmp_path, monkeypatch, isolated_schedule_db):
    """Regression (#8): the platform process never wires approval_store's per-agent
    state_db — approvals are agent-owned, the platform has no single agent_state.db.
    Its lifespan must therefore boot WITHOUT invoking the agent-side approval reconcile;
    otherwise approval_store.database() raises 'state_db not initialized' and startup
    crashes (as it does under a real `uvicorn fleetent.server:app`).

    We force _state_db=None to reproduce the fresh-process production condition that the
    other lifespan tests accidentally mask via a leaked module-global (conftest's
    _reset_traces_reflection_state_db resets traces/reflection but not approval_store).
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    monkeypatch.chdir(tmp_path)

    from fleetent.governance import approval_store

    monkeypatch.setattr(approval_store, "_state_db", None)

    import fleetent.server as srv

    # Entering the context triggers FastAPI lifespan startup; it must not raise.
    with TestClient(srv.app):
        pass
