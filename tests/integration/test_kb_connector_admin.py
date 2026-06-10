"""Tests for DB-managed KB source connectors (/admin/kb/connectors)."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.knowledge_base_management.kb_admin_api as api
import fleetent.platform.knowledge_base_management.kb_connector_store as store
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    user_store._init_db()
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> str:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id)


def _hdr(token: str, confirm: bool = False) -> dict:
    h = {"Authorization": f"Session {token}"}
    if confirm:
        h["X-Confirm"] = "true"
    return h


_GDRIVE = {
    "connector_id": "pilot-drive",
    "kind": "google_drive",
    "tenant_id": "pilot-tenant",
    "kb_id": "pilot-kb",
    "config": {
        "folder_id": "FOLDER123",
        "recursive": True,
        "access_token_env": "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN",
        "refresh_token_env": "FLEETENT_GOOGLE_DRIVE_REFRESH_TOKEN",
        "client_id_env": "FLEETENT_GOOGLE_DRIVE_CLIENT_ID",
        "client_secret_env": "FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET",
    },
}


def test_inline_token_value_encrypts_into_shared_scope(client, monkeypatch):
    import base64

    from fleetent.platform.agent_lifecycle import secret_store

    monkeypatch.setenv("FLEETENT_SECRET_KEY", base64.urlsafe_b64encode(b"0" * 32).decode())
    token = _session_for("admin")
    body = {
        "connector_id": "drive2",
        "kind": "google_drive",
        "tenant_id": "t",
        "kb_id": "k",
        # value-mode inline entry: the *_value carries the token, no env name typed
        "config": {"folder_id": "F", "access_token_env_value": "ya29-secret-token"},
    }
    r = client.post("/admin/kb/connectors", headers=_hdr(token), json=body)
    assert r.status_code == 201, r.text
    cfg = r.json()["config"]
    # inline value -> platform derives + sets the env name; raw value never in config
    assert cfg["access_token_env"] == "FLEETENT_KB_DRIVE2_ACCESS_TOKEN"
    assert "access_token_env_value" not in cfg
    assert "ya29-secret-token" not in r.text
    # value lives encrypted in the shared (cross-agent) secret scope
    assert (
        secret_store.get_decrypted(None, "FLEETENT_KB_DRIVE2_ACCESS_TOKEN") == "ya29-secret-token"
    )


def test_add_list_edit_delete_connector(client):
    token = _session_for("admin")
    r = client.post("/admin/kb/connectors", headers=_hdr(token), json=_GDRIVE)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "google_drive"
    assert body["config"]["folder_id"] == "FOLDER123"
    assert body["config"]["access_token_env"] == "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN"

    listed = client.get("/admin/kb/connectors", headers=_hdr(token)).json()
    assert any(c["connector_id"] == "pilot-drive" for c in listed)

    e = client.patch(
        "/admin/kb/connectors/pilot-drive", headers=_hdr(token), json={"enabled": False}
    )
    assert e.status_code == 200 and e.json()["enabled"] is False

    d = client.delete("/admin/kb/connectors/pilot-drive", headers=_hdr(token))
    assert d.status_code == 204
    assert not client.get("/admin/kb/connectors", headers=_hdr(token)).json()


def test_add_confluence_connector(client):
    token = _session_for("admin")
    r = client.post(
        "/admin/kb/connectors",
        headers=_hdr(token),
        json={
            "connector_id": "pilot-confluence",
            "kind": "confluence",
            "tenant_id": "pilot-tenant",
            "kb_id": "pilot-kb",
            "config": {
                "base_url": "https://example.atlassian.net/wiki",
                "scope_type": "space",
                "space_key": "EXAMPLE",
                "username_env": "FLEETENT_CONFLUENCE_USERNAME",
                "api_token_env": "FLEETENT_CONFLUENCE_TOKEN",
            },
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["config"]["space_key"] == "EXAMPLE"


def test_unknown_kind_422_and_duplicate_409(client):
    token = _session_for("admin")
    bad = client.post(
        "/admin/kb/connectors",
        headers=_hdr(token),
        json={"connector_id": "x", "kind": "dropbox", "config": {}},
    )
    assert bad.status_code == 422
    client.post("/admin/kb/connectors", headers=_hdr(token), json=_GDRIVE)
    dup = client.post("/admin/kb/connectors", headers=_hdr(token), json=_GDRIVE)
    assert dup.status_code == 409


def test_viewer_cannot_write(client):
    token = _session_for("viewer")
    assert client.post("/admin/kb/connectors", headers=_hdr(token), json=_GDRIVE).status_code == 403


def test_check_passthrough(client, monkeypatch):
    token = _session_for("admin")
    client.post("/admin/kb/connectors", headers=_hdr(token), json=_GDRIVE)

    async def _fake_check(connector_id, *, settings=None, **kw):
        # the API must feed DB-derived settings carrying our connector
        ids = [c.connector_id for c in settings.knowledge_base.google_drive.connectors]
        assert "pilot-drive" in ids
        return SimpleNamespace(connector_id=connector_id, status="ok", message="reachable")

    monkeypatch.setattr(api.knowledge_base, "check_connector", _fake_check)
    r = client.post("/admin/kb/connectors/pilot-drive/check", headers=_hdr(token))
    assert r.status_code == 200
    assert r.json() == {"connector_id": "pilot-drive", "status": "ok", "message": "reachable"}


def test_real_sync_requires_confirm(client, monkeypatch):
    token = _session_for("admin")
    client.post("/admin/kb/connectors", headers=_hdr(token), json=_GDRIVE)

    async def _fake_sync(connector_id, *, settings=None, dry_run=True, **kw):
        return SimpleNamespace(connector_id=connector_id, status="synced", summary={}, error=None)

    monkeypatch.setattr(api.knowledge_base, "run_connector_sync", _fake_sync)
    # real sync without confirm -> 428
    assert (
        client.post(
            "/admin/kb/connectors/pilot-drive/sync", headers=_hdr(token), json={"dry_run": False}
        ).status_code
        == 428
    )
    # dry-run allowed without confirm
    r = client.post(
        "/admin/kb/connectors/pilot-drive/sync", headers=_hdr(token), json={"dry_run": True}
    )
    assert r.status_code == 200 and r.json()["status"] == "synced"


def test_custom_yaml_roundtrip_and_not_in_ingestion_model(client):
    token = _session_for("admin")
    # author custom as YAML; stored as JSON, returned with a custom_yaml for display
    body = {**_GDRIVE, "custom_yaml": "poll_interval: 3600\nlabels:\n  - pilot\n"}
    r = client.post("/admin/kb/connectors", headers=_hdr(token), json=body)
    assert r.status_code == 201, r.text
    assert r.json()["custom"] == {"poll_interval": 3600, "labels": ["pilot"]}
    assert "poll_interval: 3600" in r.json()["custom_yaml"]
    # edit via YAML
    e = client.patch(
        "/admin/kb/connectors/pilot-drive", headers=_hdr(token), json={"custom_yaml": "k: v\n"}
    )
    assert e.status_code == 200 and e.json()["custom"] == {"k": "v"}
    # invalid YAML -> 422
    bad = client.patch(
        "/admin/kb/connectors/pilot-drive", headers=_hdr(token), json={"custom_yaml": "[unbalanced"}
    )
    assert bad.status_code == 422
    # non-mapping YAML -> 422
    notmap = client.patch(
        "/admin/kb/connectors/pilot-drive", headers=_hdr(token), json={"custom_yaml": "- a\n- b"}
    )
    assert notmap.status_code == 422
    # custom is metadata: it must NOT leak into the ingestion connector model
    kb = store.as_knowledge_base_settings()
    conn = kb.google_drive.connectors[0]
    assert not hasattr(conn, "poll_interval") and not hasattr(conn, "k")


def test_builder_assembles_settings(client):
    # store-level: rows -> KnowledgeBaseSettings the engine understands
    token = _session_for("admin")
    client.post("/admin/kb/connectors", headers=_hdr(token), json=_GDRIVE)
    kb = store.as_knowledge_base_settings()
    assert [c.connector_id for c in kb.google_drive.connectors] == ["pilot-drive"]
    assert kb.google_drive.connectors[0].folder_id == "FOLDER123"
