from datetime import timedelta

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.user_store as user_store
from fleetent.platform.im_gateway_management import identity as im_identity
from fleetent.platform.im_gateway_management.pending_link_store import PendingLinkStore
from fleetent.platform.user_management import user_admin_api as api
from tests.integration._migration_template import apply_migrations


def _session_headers(user: user_store.User) -> dict[str, str]:
    return {"Authorization": f"Session {auth.create_session(user.id)}"}


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    apply_migrations(tmp_path / "users.db")
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def test_link_initiate_requires_session_and_returns_code(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    user = user_store.create_web_user("viewer@example.com", "Viewer", role="viewer")
    store = PendingLinkStore(ttl=timedelta(minutes=10))
    monkeypatch.setattr(api, "_pending_links", store)
    audits: list[tuple[object, ...]] = []
    monkeypatch.setattr(api.audit_log, "write_audit", lambda *args, **kwargs: audits.append(args))

    unauthorized = client.post("/admin/link/initiate")
    assert unauthorized.status_code == 401

    response = client.post("/admin/link/initiate", headers=_session_headers(user))

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["code"], str) and payload["code"]
    pending = store.pop_valid(payload["code"])
    assert pending is not None
    assert pending.user_id == user.id
    assert pending.tenant_id == user.tenant_id
    assert audits
    assert audits[0][0] == user.id


def test_link_unlink_requires_session_unlinks_identity_and_writes_audit(
    tmp_path, monkeypatch
):
    client = _client(tmp_path, monkeypatch)
    user = user_store.create_web_user("viewer@example.com", "Viewer", role="viewer")
    im_identity.get_or_create("telegram", "424242", user.tenant_id)
    im_identity.rebind_im_identity(
        im_identity.list_all()[0]["id"],
        user.id,
    )
    audits: list[tuple[object, ...]] = []
    monkeypatch.setattr(api.audit_log, "write_audit", lambda *args, **kwargs: audits.append(args))

    unauthorized = client.post(
        "/admin/link/unlink",
        json={"platform": "telegram", "platform_user_id": "424242"},
    )
    assert unauthorized.status_code == 401

    response = client.post(
        "/admin/link/unlink",
        headers=_session_headers(user),
        json={"platform": "telegram", "platform_user_id": "424242"},
    )

    assert response.status_code == 200
    assert im_identity.list_im_identities(user.id) == []
    assert audits
    assert audits[0][0] == user.id
