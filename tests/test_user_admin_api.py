import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.api_key_store as aks
import fleetent.audit_log as audit
import fleetent.auth as auth
import fleetent.blocklist as blocklist
import fleetent.im_user_store as im_user_store
import fleetent.user_admin_api as api
import fleetent.user_store as user_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    for mod in (user_store, aks, audit, blocklist, im_user_store):
        monkeypatch.setattr(mod, "DB_PATH", tmp_path / "users.db")
    user_store._init_db()
    aks._init_db()
    audit._init_db()
    im_user_store._init_db()
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> str:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


def test_no_auth_401(client):
    assert client.get("/admin/users").status_code == 401


def test_viewer_can_read_but_not_write(client):
    token, _ = _session_for("viewer")
    assert client.get("/admin/users", headers=_hdr(token)).status_code == 200
    r = client.post(
        "/admin/users", headers=_hdr(token),
        json={"email": "x@x.com", "name": "X"},
    )
    assert r.status_code == 403


def test_admin_create_and_list_user(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/users", headers=_hdr(token),
        json={"email": "a@x.com", "name": "Alice", "password": "pw"},
    )
    assert r.status_code == 201
    listed = client.get("/admin/users", headers=_hdr(token)).json()
    assert any(u["email"] == "a@x.com" for u in listed)


def test_admin_issue_and_revoke_key(client):
    token, _ = _session_for("admin")
    uid = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "b@x.com", "name": "Bob"}
    ).json()["id"]
    issued = client.post(
        f"/admin/users/{uid}/keys", headers=_hdr(token), json={"scope": ["ops-bot"]}
    ).json()
    assert issued["plaintext"].startswith("ma-")
    key_id = issued["key"]["id"]
    assert client.delete(f"/admin/keys/{key_id}", headers=_hdr(token)).status_code == 204
    assert aks.resolve(issued["plaintext"]) is None


def test_admin_block_user_and_audit(client):
    token, admin_id = _session_for("admin")
    uid = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "c@x.com", "name": "Cara"}
    ).json()["id"]
    r = client.post(f"/admin/users/{uid}/block", headers=_hdr(token), json={"reason": "abuse"})
    assert r.status_code == 200
    assert user_store.get_by_id(uid).status == "blocked"
    audit_rows = client.get("/admin/audit?action=block_user", headers=_hdr(token)).json()
    assert any(row["target_id"] == uid for row in audit_rows)


def test_im_user_block_restore(client):
    token, _ = _session_for("admin")
    u = im_user_store.get_or_create("slack", "U1")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    assert client.post(
        f"/admin/im-users/{im_id}/block", headers=_hdr(token), json={"reason": "x"}
    ).status_code == 200
    assert im_user_store.check_allowed_by_user_id(u.id) is False
    assert client.post(
        f"/admin/im-users/{im_id}/restore", headers=_hdr(token), json={"reason": "ok"}
    ).status_code == 200
    assert im_user_store.check_allowed_by_user_id(u.id) is True
