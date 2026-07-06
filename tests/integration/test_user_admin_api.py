import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.platform.user_management.api_key_store as aks
import fleetent.platform.user_management.user_admin_api as api
import fleetent.user_store as user_store
from fleetent.platform.im_gateway_management import identity as im_user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> str:
    u, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


def test_no_auth_401(client):
    assert client.get("/admin/users").status_code == 401


def test_login_success_and_me(client):
    u = user_store.create_web_user("log@x.com", "Logger", password_hash=auth.hash_password("pw"))
    user_store.set_role(u.id, "admin")
    r = client.post("/admin/login", json={"email": "log@x.com", "password": "pw"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert r.json()["must_reset"] is False
    me = client.get("/admin/me", headers=_hdr(token))
    assert me.json()["email"] == "log@x.com"


def test_builtin_admin_login_by_username(client):
    # Builtin admin is seeded with email=None; login form sends the "Username" field.
    # admin/admin must resolve the builtin admin by name, not only by email.
    seeded = auth.seed_builtin_admin()
    assert seeded is not None
    r = client.post(
        "/admin/login",
        json={"email": auth.BUILTIN_ADMIN_NAME, "password": auth.BUILTIN_ADMIN_PASSWORD},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    assert r.json()["must_reset"] is True  # default admin must change password first


def test_admin_resets_user_password(client):
    u = user_store.create_web_user("x@x.com", "X", password_hash=auth.hash_password("old"))
    token, _ = _session_for("admin")
    r = client.post(
        f"/admin/users/{u.id}/password",
        json={"new_password": "brandnew"},
        headers=_hdr(token),
    )
    assert r.status_code == 200
    refreshed = user_store.get_by_id(u.id)
    assert auth.verify_password("brandnew", refreshed.password_hash)
    assert refreshed.must_reset == 1  # target forced to reset on next login


def test_viewer_cannot_reset_password(client):
    u = user_store.create_web_user("y@x.com", "Y")
    token, _ = _session_for("viewer")
    r = client.post(
        f"/admin/users/{u.id}/password", json={"new_password": "z"}, headers=_hdr(token)
    )
    assert r.status_code == 403


def test_reset_password_unknown_user_404(client):
    token, _ = _session_for("admin")
    r = client.post("/admin/users/ghost/password", json={"new_password": "z"}, headers=_hdr(token))
    assert r.status_code == 404


def test_login_bad_password_401(client):
    user_store.create_web_user("a@x.com", "A", password_hash=auth.hash_password("right"))
    assert (
        client.post("/admin/login", json={"email": "a@x.com", "password": "wrong"}).status_code
        == 401
    )


def test_blocked_account_cannot_login(client):
    u = user_store.create_web_user("b@x.com", "B", password_hash=auth.hash_password("pw"))
    user_store.set_status(u.id, "blocked")
    assert (
        client.post("/admin/login", json={"email": "b@x.com", "password": "pw"}).status_code == 403
    )


def test_must_reset_gate_then_change_password(client):
    u = user_store.create_web_user(
        "m@x.com", "M", password_hash=auth.hash_password("temp"), must_reset=True, role="admin"
    )
    token = client.post("/admin/login", json={"email": "m@x.com", "password": "temp"}).json()[
        "token"
    ]
    hdr = _hdr(token)
    assert client.get("/admin/users", headers=hdr).status_code == 403  # gated
    assert (
        client.post(
            "/admin/change-password", json={"new_password": "newpw"}, headers=hdr
        ).status_code
        == 200
    )
    assert client.get("/admin/users", headers=hdr).status_code == 200  # gate cleared
    assert user_store.get_by_id(u.id).must_reset == 0


def test_im_users_list(client):
    token, _ = _session_for("admin")
    im_user_store.get_or_create("slack", "U_LIST", "default")
    rows = client.get("/admin/im-users", headers=_hdr(token)).json()
    assert any(r["platform_user_id"] == "U_LIST" for r in rows)


def test_im_fields_endpoint_lists_per_platform(client):
    token, _ = _session_for("viewer")  # read-only callers may load the field schema
    r = client.get("/admin/im-users/fields", headers=_hdr(token))
    assert r.status_code == 200
    body = r.json()
    assert "slack" in body and "telegram" in body and "whatsapp" in body
    slack_keys = {f["key"] for f in body["slack"]}
    assert "email" in slack_keys
    assert "username" not in slack_keys  # telegram-only


def test_im_identity_edit_metadata(client):
    token, _ = _session_for("admin")
    user = im_user_store.get_or_create("slack", "U_EDIT", "default")
    im_id = im_user_store.list_im_identities(user.id)[0]["id"]
    r = client.patch(
        f"/admin/im-users/{im_id}",
        headers=_hdr(token),
        json={"metadata": {"display_name": "Alice", "email": "a@x.com"}},
    )
    assert r.status_code == 200
    row = im_user_store.get_im_user(im_id)
    assert row["metadata"] == {"display_name": "Alice", "email": "a@x.com"}
    # the platform handle is never touched by an edit
    assert row["platform_user_id"] == "U_EDIT"


def test_im_identity_edit_missing_404(client):
    token, _ = _session_for("admin")
    r = client.patch(
        "/admin/im-users/999999",
        headers=_hdr(token),
        json={"metadata": {"display_name": "x"}},
    )
    assert r.status_code == 404


def test_im_identity_delete(client):
    token, _ = _session_for("admin")
    user = im_user_store.get_or_create("slack", "U_DEL", "default")
    im_id = im_user_store.list_im_identities(user.id)[0]["id"]
    r = client.delete(f"/admin/im-users/{im_id}", headers=_hdr(token))
    assert r.status_code == 204
    assert im_user_store.get_im_user(im_id) is None


def test_im_identity_delete_missing_404(client):
    token, _ = _session_for("admin")
    r = client.delete("/admin/im-users/999999", headers=_hdr(token))
    assert r.status_code == 404


def test_im_identity_edit_and_delete_require_admin(client):
    token, _ = _session_for("viewer")
    user = im_user_store.get_or_create("slack", "U_VIEW", "default")
    im_id = im_user_store.list_im_identities(user.id)[0]["id"]
    assert (
        client.patch(
            f"/admin/im-users/{im_id}",
            headers=_hdr(token),
            json={"metadata": {"display_name": "z"}},
        ).status_code
        == 403
    )
    assert client.delete(f"/admin/im-users/{im_id}", headers=_hdr(token)).status_code == 403


def test_viewer_can_read_but_not_write(client):
    token, _ = _session_for("viewer")
    assert client.get("/admin/users", headers=_hdr(token)).status_code == 200
    r = client.post(
        "/admin/users",
        headers=_hdr(token),
        json={"email": "x@x.com", "name": "X"},
    )
    assert r.status_code == 403


def test_admin_create_and_list_user(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/users",
        headers=_hdr(token),
        json={"email": "a@x.com", "name": "Alice", "password": "pw"},
    )
    assert r.status_code == 201
    listed = client.get("/admin/users", headers=_hdr(token)).json()
    assert any(u["email"] == "a@x.com" for u in listed)


def test_created_user_logs_in_with_initial_password_and_must_reset(client):
    token, _ = _session_for("admin")
    client.post(
        "/admin/users",
        headers=_hdr(token),
        json={"email": "n@x.com", "name": "New", "password": "initpw", "must_reset": True},
    )
    r = client.post("/admin/login", json={"email": "n@x.com", "password": "initpw"})
    assert r.status_code == 200
    assert r.json()["must_reset"] is True  # forced to change on first login


def test_create_users_with_empty_email_allowed(client):
    # Empty email means "no email"; it must not collide with another empty-email user.
    token, _ = _session_for("admin")
    r1 = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "", "name": "A", "password": "pw"}
    )
    assert r1.status_code == 201
    assert r1.json()["email"] is None
    r2 = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "  ", "name": "B", "password": "pw"}
    )
    assert r2.status_code == 201  # not a false "email already exists"


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


def test_admin_audit_filters_by_time_range(client):
    token, _ = _session_for("admin")
    uid = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "tr@x.com", "name": "Tr"}
    ).json()["id"]
    client.post(f"/admin/users/{uid}/block", headers=_hdr(token), json={"reason": "abuse"})

    # An `until` in the far past excludes the just-written row.
    past = client.get(
        "/admin/audit?action=block_user&until=2000-01-01T00:00:00", headers=_hdr(token)
    ).json()
    assert past == []

    # A wide since/until window includes it.
    ranged = client.get(
        "/admin/audit?action=block_user&since=2000-01-01T00:00:00&until=2999-01-01T00:00:00",
        headers=_hdr(token),
    ).json()
    assert any(row["target_id"] == uid for row in ranged)


def test_last_active_admin_role_block_and_delete_are_rejected(client):
    token, admin_id = _session_for("admin")

    role_response = client.patch(
        f"/admin/users/{admin_id}/role", headers=_hdr(token), json={"role": "viewer"}
    )
    assert role_response.status_code == 403
    assert user_store.get_by_id(admin_id).role == "admin"

    block_response = client.post(
        f"/admin/users/{admin_id}/block", headers=_hdr(token), json={"reason": "self-lock"}
    )
    assert block_response.status_code == 403
    assert user_store.get_by_id(admin_id).status == "active"

    delete_response = client.delete(f"/admin/users/{admin_id}", headers=_hdr(token))
    assert delete_response.status_code == 403
    assert user_store.get_by_id(admin_id) is not None


def test_admin_role_can_be_transferred_when_another_active_admin_exists(client):
    token, admin_id = _session_for("admin")
    target = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "next@x.com", "name": "Next"}
    ).json()

    promote_response = client.patch(
        f"/admin/users/{target['id']}/role", headers=_hdr(token), json={"role": "admin"}
    )
    assert promote_response.status_code == 200

    demote_self_response = client.patch(
        f"/admin/users/{admin_id}/role", headers=_hdr(token), json={"role": "viewer"}
    )
    assert demote_self_response.status_code == 200
    assert user_store.get_by_id(admin_id).role == "viewer"
    assert user_store.get_by_id(target["id"]).role == "admin"


def test_admin_rebind_im_identity_to_user(client):
    token, _ = _session_for("admin")
    target = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "t@x.com", "name": "Target"}
    ).json()["id"]
    u = im_user_store.get_or_create("slack", "U_BIND", "default")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]

    r = client.post(f"/admin/im-users/{im_id}/bind", headers=_hdr(token), json={"user_id": target})
    assert r.status_code == 200
    rows = client.get("/admin/im-users", headers=_hdr(token)).json()
    row = next(x for x in rows if x["id"] == im_id)
    assert row["user_id"] == target  # rebound to the chosen user


def test_rebind_unknown_user_404(client):
    token, _ = _session_for("admin")
    u = im_user_store.get_or_create("slack", "U_BIND2", "default")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    r = client.post(f"/admin/im-users/{im_id}/bind", headers=_hdr(token), json={"user_id": "ghost"})
    assert r.status_code == 404


def test_viewer_cannot_rebind_im(client):
    token, _ = _session_for("viewer")
    r = client.post("/admin/im-users/1/bind", headers=_hdr(token), json={"user_id": "x"})
    assert r.status_code == 403


def test_im_user_block_restore(client):
    token, _ = _session_for("admin")
    u = im_user_store.get_or_create("slack", "U1", "default")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    assert (
        client.post(
            f"/admin/im-users/{im_id}/block", headers=_hdr(token), json={"reason": "x"}
        ).status_code
        == 200
    )
    assert user_store.get_by_id(u.id).status == "blocked"
    assert (
        client.post(
            f"/admin/im-users/{im_id}/restore", headers=_hdr(token), json={"reason": "ok"}
        ).status_code
        == 200
    )
    assert user_store.get_by_id(u.id).status == "active"
    assert client.post(f"/admin/im-users/{im_id}/approve", headers=_hdr(token)).status_code == 404
    assert client.get("/admin/im-users/pending", headers=_hdr(token)).status_code in {404, 405}


# --- edit user profile (name/email) -------------------------------------------


def test_update_user_edits_name_and_email(client):
    token, _ = _session_for("admin")
    target, _ = user_store.create_user("old-name", email="old@x.io")
    r = client.patch(
        f"/admin/users/{target.id}",
        json={"name": "new-name", "email": "new@x.io"},
        headers=_hdr(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "new-name"
    assert body["email"] == "new@x.io"
    refreshed = user_store.get_by_id(target.id)
    assert refreshed.name == "new-name" and refreshed.email == "new@x.io"


def test_update_user_partial_name_only(client):
    token, _ = _session_for("admin")
    target, _ = user_store.create_user("keep-mail", email="keep@x.io")
    r = client.patch(f"/admin/users/{target.id}", json={"name": "renamed"}, headers=_hdr(token))
    assert r.status_code == 200
    refreshed = user_store.get_by_id(target.id)
    assert refreshed.name == "renamed" and refreshed.email == "keep@x.io"


def test_update_user_unknown_404(client):
    token, _ = _session_for("admin")
    r = client.patch("/admin/users/nope", json={"name": "x"}, headers=_hdr(token))
    assert r.status_code == 404


def test_update_user_viewer_forbidden(client):
    token, _ = _session_for("viewer")
    target, _ = user_store.create_user("victim")
    r = client.patch(f"/admin/users/{target.id}", json={"name": "x"}, headers=_hdr(token))
    assert r.status_code == 403


def test_update_user_email_conflict_409(client):
    token, _ = _session_for("admin")
    user_store.create_user("a", email="taken@x.io")
    target, _ = user_store.create_user("b", email="b@x.io")
    r = client.patch(f"/admin/users/{target.id}", json={"email": "taken@x.io"}, headers=_hdr(token))
    assert r.status_code == 409
