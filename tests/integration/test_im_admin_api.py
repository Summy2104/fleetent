"""Tests for im_admin_api (/admin/im). Connector registry + channel allowlist REST.

Auth follows the console pattern (Session header + role). The connector manager is
reached through injectable start/stop seams so tests need no asyncio / real adapters.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.platform.im_gateway_management.admin_api as api
import fleetent.platform.im_gateway_management.channel_allowlist as allowlist
import fleetent.platform.im_gateway_management.connector_config as cfg
import fleetent.platform.im_gateway_management.connector_store as store
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
    owner = user_store.admin_owner_id()
    store.upsert_connector(
        owner, "slack", config='{"bot_token": "xoxb-secret123", "app_token": "x"}'
    )
    store.set_enabled(owner, "slack", True)
    started: list = []
    stopped: list = []
    monkeypatch.setattr(api, "start_connector", lambda o, p: started.append((o, p)))
    monkeypatch.setattr(api, "stop_connector", lambda o, p: stopped.append((o, p)))
    api._started, api._stopped = started, stopped  # type: ignore[attr-defined]
    api._owner = owner  # type: ignore[attr-defined]
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
    # each row carries its owner_id
    assert slack["owner_id"] == api._owner  # type: ignore[attr-defined]


def test_list_connectors_admin_sees_all_owners(client):
    # a second owner's connector must also be visible to the admin
    store.upsert_connector("ownerZ", "telegram", config='{"bot_token": "tg"}')
    token = _session_for("admin")
    r = client.get("/admin/im/connectors", headers=_hdr(token))
    owners = {c["owner_id"] for c in r.json()}
    assert "ownerZ" in owners and api._owner in owners  # type: ignore[attr-defined]


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
    assert cfg.resolve(api._owner, "slack")["bot_token"] == "new-tok"  # type: ignore[attr-defined]
    assert store.get_connector(api._owner, "slack")["allowlist_enforced"] == 1  # type: ignore[attr-defined]


def test_enable_disable_drive_manager(client):
    owner = api._owner  # type: ignore[attr-defined]
    token = _session_for("admin")
    assert client.post("/admin/im/connectors/slack/disable", headers=_hdr(token)).status_code == 200
    assert store.get_connector(owner, "slack")["enabled"] == 0
    assert api._stopped == [(owner, "slack")]  # type: ignore[attr-defined]
    assert client.post("/admin/im/connectors/slack/enable", headers=_hdr(token)).status_code == 200
    assert store.get_connector(owner, "slack")["enabled"] == 1
    assert api._started == [(owner, "slack")]  # type: ignore[attr-defined]


def test_create_connector_new_platform(client):
    token = _session_for("admin")
    r = client.post(
        "/admin/im/connectors",
        headers=_hdr(token),
        json={
            "platform": "whatsapp",
            "config": {
                "phone_number_id": "123",
                "access_token": "EAAG1234567890wxyz",
                "verify_token": "vt",
                "business_account_id": "ba1",
            },
        },
    )
    assert r.status_code == 201
    assert r.json()["platform"] == "whatsapp"
    # masked on read
    assert r.json()["config"]["access_token"].endswith("wxyz")
    assert cfg.resolve(api._owner, "whatsapp")["access_token"] == "EAAG1234567890wxyz"  # type: ignore[attr-defined]


def test_create_connector_existing_platform_updates_no_duplicate(client):
    token = _session_for("admin")
    r = client.post(
        "/admin/im/connectors",
        headers=_hdr(token),
        json={"platform": "slack", "config": {"bot_token": "xoxb-updated"}},
    )
    assert r.status_code == 201
    assert cfg.resolve(api._owner, "slack")["bot_token"] == "xoxb-updated"  # type: ignore[attr-defined]
    assert len([c for c in store.list_connectors() if c["platform"] == "slack"]) == 1


def test_create_connector_viewer_forbidden(client):
    token = _session_for("viewer")
    r = client.post(
        "/admin/im/connectors",
        headers=_hdr(token),
        json={"platform": "telegram", "config": {"bot_token": "t"}},
    )
    assert r.status_code == 403
    assert store.get_connector(api._owner, "telegram") is None  # type: ignore[attr-defined]


def test_create_connector_unknown_platform_rejected(client):
    token = _session_for("admin")
    r = client.post(
        "/admin/im/connectors",
        headers=_hdr(token),
        json={"platform": "discord", "config": {"bot_token": "t"}},
    )
    assert r.status_code == 422
    assert store.get_connector(api._owner, "discord") is None  # type: ignore[attr-defined]


_ADMIN_HTML = (Path(__file__).parents[2] / "src" / "fleetent" / "static" / "admin.html").read_text(
    encoding="utf-8"
)


def test_ui_has_connectors_in_users_tab_and_add_modal():
    html = _ADMIN_HTML
    # connectors are managed inside the unified Users tab — no standalone IM/connectors tab
    assert 'data-tab="connectors"' not in html
    assert 'id="tab-im"' not in html
    # "Add connection" is a per-User-row action, not a top-level bar
    assert "conn-create-bar" not in html
    assert 'id="conn-modal"' in html
    assert "openConnModal(" in html
    assert "createConn(" in html
    # platform dropdown with the three platforms
    assert 'id="conn-platform"' in html
    for p in ("telegram", "slack", "whatsapp"):
        assert f'value="{p}"' in html


def test_ui_connector_field_schema_matches_backend():
    html = _ADMIN_HTML
    # The per-platform credential field map must list exactly the backend keys.
    for platform, keys in cfg.PLATFORM_CONFIG_KEYS.items():
        for key in keys:
            assert key in html, f"missing field {key} for {platform} in admin.html"


def test_ui_has_enable_disable_and_admin_gate():
    html = _ADMIN_HTML
    assert "connEnable(" in html and "connDisable(" in html
    # per-row connector controls (incl. Add connection) are admin-gated
    body = html.split("function renderUsers()", 1)[1].split("function closeMenus", 1)[0]
    assert "IS_VIEWER" in body
    assert "openConnModal('" in body


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
