import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.governance.blocklist as blocklist
import fleetent.platform.user_management.api_key_store as aks
import fleetent.platform.user_management.user_admin_api as api
import fleetent.user_store as user_store
from fleetent.platform.im_gateway_management import identity as im_user_store


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


def test_ui_served(client):
    r = client.get("/admin/ui")
    assert r.status_code == 200
    assert "fleetent" in r.text and "Admin" in r.text


def test_ui_has_kb_tab(client):
    r = client.get("/admin/ui")
    assert 'data-tab="kb"' in r.text  # knowledge-base console tab present
    assert "/kb/search" in r.text


def test_ui_persists_session_across_refresh(client):
    # Session token must survive a page reload: persisted to localStorage on login,
    # restored on boot. Without this the SPA falls back to the login view every refresh.
    html = client.get("/admin/ui").text
    assert "localStorage.setItem" in html  # token saved on login
    assert "localStorage.getItem" in html  # token restored on boot
    assert "localStorage.removeItem" in html  # token cleared on logout / 401


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
    assert r.json()["role"] == "built_in_admin"
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


def test_ui_auth_uses_semantic_forms(client):
    # login / reset / create wrapped in <form> with proper autocomplete so the browser's
    # password manager behaves like a normal site (fewer stray save prompts).
    html = client.get("/admin/ui").text
    assert html.count("<form") >= 3
    assert 'autocomplete="current-password"' in html
    assert 'autocomplete="new-password"' in html


def test_ui_create_user_uses_modal(client):
    html = client.get("/admin/ui").text
    assert "openCreateModal" in html  # "Create user" opens a popup dialog
    assert 'id="create-modal"' in html  # modal container present
    assert "closeCreateModal" in html  # dialog can be dismissed
    assert 'id="nu-password"' in html  # initial password so the new user can log in


def test_ui_user_table_columns(client):
    html = client.get("/admin/ui").text
    assert 'id="user-filter"' in html  # client-side filter box over the list
    assert 'id="role-filter"' in html  # filter by role
    assert 'id="status-filter"' in html  # filter by status
    assert "/password" in html  # per-row admin password-reset action wired
    assert "<th>#</th>" in html  # leading row-index column
    assert "<th>Email</th>" in html  # email is its own column
    assert "<th>Nickname</th>" in html  # name column renamed and split out


def test_ui_row_actions_use_dropdown_menu(client):
    html = client.get("/admin/ui").text
    assert "toggleMenu" in html  # the "…" button toggles an overflow menu
    assert "menu-items" in html  # dropdown container for row actions
    assert "Reset password" in html  # menu entries include reset password
    assert "closeMenus" in html  # click-outside closes open menus


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
    im_user_store.get_or_create("owner1", "slack", "U_LIST")
    rows = client.get("/admin/im-users", headers=_hdr(token)).json()
    assert any(r["platform_user_id"] == "U_LIST" for r in rows)


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


def test_high_risk_delete_without_2fa_blocked_then_proceeds(client):
    token, admin_id = _session_for("admin")
    secret = auth.enable_2fa(admin_id)
    uid = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "d@x.com", "name": "D"}
    ).json()["id"]

    # No 2FA code → rejected, target user untouched (no business change).
    r = client.delete(f"/admin/users/{uid}", headers=_hdr(token))
    assert r.status_code == 403
    assert user_store.get_by_id(uid) is not None

    # Valid code → proceeds and is audited.
    r2 = client.delete(
        f"/admin/users/{uid}", headers={**_hdr(token), "X-2FA-Code": auth.totp(secret)}
    )
    assert r2.status_code == 204
    assert user_store.get_by_id(uid) is None
    audit_rows = client.get("/admin/audit?action=delete_user", headers=_hdr(token)).json()
    assert any(row["target_id"] == uid for row in audit_rows)


def test_high_risk_block_wrong_2fa_code_blocked(client):
    token, admin_id = _session_for("admin")
    auth.enable_2fa(admin_id)
    uid = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "e@x.com", "name": "E"}
    ).json()["id"]
    r = client.post(
        f"/admin/users/{uid}/block",
        headers={**_hdr(token), "X-2FA-Code": "000000"},
        json={"reason": "x"},
    )
    assert r.status_code == 403
    assert user_store.get_by_id(uid).status == "active"  # not blocked


def test_high_risk_set_role_requires_2fa(client):
    token, admin_id = _session_for("admin")
    secret = auth.enable_2fa(admin_id)
    uid = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "f@x.com", "name": "F"}
    ).json()["id"]
    assert (
        client.patch(
            f"/admin/users/{uid}/role", headers=_hdr(token), json={"role": "admin"}
        ).status_code
        == 403
    )
    ok = client.patch(
        f"/admin/users/{uid}/role",
        headers={**_hdr(token), "X-2FA-Code": auth.totp(secret)},
        json={"role": "admin"},
    )
    assert ok.status_code == 200
    assert user_store.get_by_id(uid).role == "admin"


def test_admin_rebind_im_identity_to_user(client):
    token, _ = _session_for("admin")
    target = client.post(
        "/admin/users", headers=_hdr(token), json={"email": "t@x.com", "name": "Target"}
    ).json()["id"]
    u = im_user_store.get_or_create("owner1", "slack", "U_BIND")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]

    r = client.post(f"/admin/im-users/{im_id}/bind", headers=_hdr(token), json={"user_id": target})
    assert r.status_code == 200
    rows = client.get("/admin/im-users", headers=_hdr(token)).json()
    row = next(x for x in rows if x["id"] == im_id)
    assert row["user_id"] == target  # rebound to the chosen user


def test_rebind_unknown_user_404(client):
    token, _ = _session_for("admin")
    u = im_user_store.get_or_create("owner1", "slack", "U_BIND2")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    r = client.post(f"/admin/im-users/{im_id}/bind", headers=_hdr(token), json={"user_id": "ghost"})
    assert r.status_code == 404


def test_viewer_cannot_rebind_im(client):
    token, _ = _session_for("viewer")
    r = client.post("/admin/im-users/1/bind", headers=_hdr(token), json={"user_id": "x"})
    assert r.status_code == 403


def test_ui_im_users_has_bind_action(client):
    html = client.get("/admin/ui").text
    assert "openBindModal" in html  # IM row "Bind" opens a user-picker dialog
    assert 'id="bind-modal"' in html


def test_im_user_block_restore(client):
    token, _ = _session_for("admin")
    u = im_user_store.get_or_create("owner1", "slack", "U1")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    assert (
        client.post(
            f"/admin/im-users/{im_id}/block", headers=_hdr(token), json={"reason": "x"}
        ).status_code
        == 200
    )
    assert im_user_store.check_allowed_by_user_id(u.id) is False
    assert (
        client.post(
            f"/admin/im-users/{im_id}/restore", headers=_hdr(token), json={"reason": "ok"}
        ).status_code
        == 200
    )
    assert im_user_store.check_allowed_by_user_id(u.id) is True


# --- edit user profile (name/email) -------------------------------------------


def test_update_user_edits_name_and_email(client):
    token, _ = _session_for("admin")
    target = user_store.create_user("old-name", email="old@x.io")
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
    target = user_store.create_user("keep-mail", email="keep@x.io")
    r = client.patch(
        f"/admin/users/{target.id}", json={"name": "renamed"}, headers=_hdr(token)
    )
    assert r.status_code == 200
    refreshed = user_store.get_by_id(target.id)
    assert refreshed.name == "renamed" and refreshed.email == "keep@x.io"


def test_update_user_unknown_404(client):
    token, _ = _session_for("admin")
    r = client.patch("/admin/users/nope", json={"name": "x"}, headers=_hdr(token))
    assert r.status_code == 404


def test_update_user_viewer_forbidden(client):
    token, _ = _session_for("viewer")
    target = user_store.create_user("victim")
    r = client.patch(
        f"/admin/users/{target.id}", json={"name": "x"}, headers=_hdr(token)
    )
    assert r.status_code == 403


def test_update_user_email_conflict_409(client):
    token, _ = _session_for("admin")
    user_store.create_user("a", email="taken@x.io")
    target = user_store.create_user("b", email="b@x.io")
    r = client.patch(
        f"/admin/users/{target.id}", json={"email": "taken@x.io"}, headers=_hdr(token)
    )
    assert r.status_code == 409
