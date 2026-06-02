"""Tests for im_admin_api (/admin/im). Connector registry + channel allowlist REST.

Auth follows the console pattern (Session header + role). The connector manager is
reached through injectable start/stop seams so tests need no asyncio / real adapters.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.platform.im_gateway_management.im_admin_api as api
import fleetent.platform.im_gateway_management.im_channel_allowlist as allowlist
import fleetent.platform.im_gateway_management.im_connector_config as cfg
import fleetent.platform.im_gateway_management.im_connector_store as store
import fleetent.user_store as user_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(user_store, "DB_PATH", db_path)
    monkeypatch.setattr(store, "DB_PATH", db_path)
    user_store._init_db()
    store._init_db()
    allowlist._init_db()
    store.upsert_connector("slack", config='{"bot_token": "xoxb-secret123", "app_token": "x"}')
    store.set_enabled("slack", True)
    started: list[str] = []
    stopped: list[str] = []
    monkeypatch.setattr(api, "start_connector", lambda p: started.append(p))
    monkeypatch.setattr(api, "stop_connector", lambda p: stopped.append(p))
    api._started, api._stopped = started, stopped  # type: ignore[attr-defined]
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> str:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id)


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


def test_non_admin_forbidden(client):
    token = _session_for("viewer")
    assert client.get("/admin/im/connectors", headers=_hdr(token)).status_code == 403


def test_no_auth_401(client):
    assert client.get("/admin/im/connectors").status_code == 401


def test_list_connectors_masked(client):
    token = _session_for("admin")
    r = client.get("/admin/im/connectors", headers=_hdr(token))
    assert r.status_code == 200
    slack = next(c for c in r.json() if c["platform"] == "slack")
    # token masked: only last 4 chars retained
    assert slack["config"]["bot_token"].endswith("t123")
    assert "xoxb-secret" not in slack["config"]["bot_token"]


def test_get_connector_detail(client):
    token = _session_for("admin")
    r = client.get("/admin/im/connectors/slack", headers=_hdr(token))
    assert r.status_code == 200
    assert r.json()["platform"] == "slack"


def test_patch_connector_config_and_enforce(client):
    token = _session_for("admin")
    r = client.patch(
        "/admin/im/connectors/slack",
        headers=_hdr(token),
        json={"config": {"bot_token": "new-tok"}, "allowlist_enforced": True},
    )
    assert r.status_code == 200
    assert cfg.resolve("slack")["bot_token"] == "new-tok"
    assert store.get_connector("slack")["allowlist_enforced"] == 1


def test_enable_disable_drive_manager(client):
    token = _session_for("admin")
    assert client.post("/admin/im/connectors/slack/disable", headers=_hdr(token)).status_code == 200
    assert store.get_connector("slack")["enabled"] == 0
    assert api._stopped == ["slack"]  # type: ignore[attr-defined]
    assert client.post("/admin/im/connectors/slack/enable", headers=_hdr(token)).status_code == 200
    assert store.get_connector("slack")["enabled"] == 1
    assert api._started == ["slack"]  # type: ignore[attr-defined]


def test_allowlist_crud(client):
    token = _session_for("admin")
    r = client.post(
        "/admin/im/allowlist",
        headers=_hdr(token),
        json={"platform": "slack", "scope_type": "channel", "scope_id": "C1"},
    )
    assert r.status_code == 201
    entries = client.get("/admin/im/allowlist?platform=slack", headers=_hdr(token)).json()
    assert len(entries) == 1
    entry_id = entries[0]["id"]
    assert client.delete(f"/admin/im/allowlist/{entry_id}", headers=_hdr(token)).status_code == 200
    assert client.get("/admin/im/allowlist?platform=slack", headers=_hdr(token)).json() == []
