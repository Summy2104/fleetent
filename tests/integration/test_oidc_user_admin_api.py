from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.platform.user_management.user_admin_api as api
import fleetent.user_store as user_store
from fleetent.platform.im_gateway_management import identity as im_user_store
from fleetent.platform.tenancy import store as tenancy_store
from fleetent.platform.user_management.oidc import OidcIdentity, OidcSettings
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode("ascii"))
    auth._SESSIONS.clear()
    apply_migrations(tmp_path / "users.db")
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _enable_oidc(
    monkeypatch,
    email: str,
    allowed_email_domains: list[str] | None = None,
    button_label: str = "",
):
    if tenancy_store.get_tenant("acme") is None:
        tenancy_store.create_tenant(id="acme", name="Acme")
    monkeypatch.setattr(
        api,
        "_oidc_settings",
        lambda: OidcSettings(
            enabled=True,
            issuer="https://idp.example.com/realms/acme",
            client_id="fleetent-web",
            client_secret_env="FLEETENT_OIDC_CLIENT_SECRET",
            redirect_uri="https://fleetent.example.com/admin/oidc/callback",
            button_label=button_label,
            tenant="acme",
            allowed_email_domains=allowed_email_domains or [],
        ),
    )

    class _FakeOidcRelyingParty:
        def __init__(self, settings: OidcSettings) -> None:
            self.settings = settings

        def build_authorize_url(self, *, state: str, nonce: str) -> str:
            return (
                "https://idp.example.com/oauth2/authorize"
                f"?state={state}&nonce={nonce}&redirect_uri={self.settings.redirect_uri}"
            )

        def exchange_code(
            self,
            *,
            code: str,
            state: str,
            expected_state: str,
            nonce: str,
            expected_nonce: str,
        ) -> OidcIdentity:
            assert code == "good-code"
            assert state == expected_state
            assert nonce == expected_nonce
            return OidcIdentity(
                email=email,
                claims={"sub": "oidc-user", "email": email, "email_verified": True},
            )

    monkeypatch.setattr(api, "OidcRelyingParty", _FakeOidcRelyingParty)


def _session_user_from_redirect(location: str) -> user_store.User:
    params = parse_qs(urlparse(location).query)
    token = params["token"][0]
    user_id = auth.validate_session(token, idle_timeout=300)
    assert user_id is not None
    user = user_store.get_by_id(user_id)
    assert user is not None
    return user


def _callback_with_fresh_flow(client: TestClient):
    login = client.get("/admin/oidc/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    return client.get(
        "/admin/oidc/callback",
        params={"code": "good-code", "state": state},
        follow_redirects=False,
    )


def test_oidc_config_reports_disabled_without_auth_or_sensitive_fields(client):
    response = client.get("/admin/oidc/config")

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "label": ""}
    assert set(response.json()) == {"enabled", "label"}
    assert "client_secret" not in response.text
    assert "issuer" not in response.text
    assert "client_id" not in response.text


def test_oidc_config_reports_enabled_label_without_leaking_sensitive_fields(client, monkeypatch):
    _enable_oidc(monkeypatch, "person@example.com", button_label="Sign in with Google")

    response = client.get("/admin/oidc/config")

    assert response.status_code == 200
    assert response.json() == {"enabled": True, "label": "Sign in with Google"}
    assert set(response.json()) == {"enabled", "label"}
    assert "FLEETENT_OIDC_CLIENT_SECRET" not in response.text
    assert "https://idp.example.com/realms/acme" not in response.text
    assert "fleetent-web" not in response.text
    assert "client_secret" not in response.text
    assert "issuer" not in response.text
    assert "client_id" not in response.text


def test_oidc_login_redirects_to_idp_and_sets_flow_cookie(client, monkeypatch):
    _enable_oidc(monkeypatch, "person@example.com")

    response = client.get("/admin/oidc/login", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://idp.example.com/oauth2/authorize?")
    assert "fleetent_oidc_flow=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]


def test_oidc_callback_provisions_email_user_and_creates_session(client, monkeypatch):
    email = "new.person@example.com"
    _enable_oidc(monkeypatch, email)

    login = client.get("/admin/oidc/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

    response = client.get(
        "/admin/oidc/callback",
        params={"code": "good-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    user = _session_user_from_redirect(response.headers["location"])
    assert user.email == email
    assert user.tenant_id == "acme"
    assert user.role == "viewer"
    assert im_user_store.list_im_identities(user.id) == []


def test_oidc_callback_rejects_disallowed_email_domain_without_session_or_user(
    client,
    monkeypatch,
):
    email = "person@gmail.com"
    _enable_oidc(monkeypatch, email, allowed_email_domains=["acme.com"])
    sessions_before = set(auth._SESSIONS)

    response = _callback_with_fresh_flow(client)

    assert response.status_code == 403
    assert response.json()["detail"] == "email domain not allowed"
    assert "location" not in response.headers
    assert set(auth._SESSIONS) == sessions_before
    assert user_store.get_by_email("acme", email) is None


def test_oidc_callback_allows_configured_email_domain(client, monkeypatch):
    email = "Alice@ACME.com"
    _enable_oidc(monkeypatch, email, allowed_email_domains=["acme.com"])

    response = _callback_with_fresh_flow(client)

    assert response.status_code == 302
    user = _session_user_from_redirect(response.headers["location"])
    assert user.email == email.lower()
    assert user.tenant_id == "acme"


def test_oidc_callback_rejects_existing_user_with_disallowed_email_domain(
    client,
    monkeypatch,
):
    email = "existing.person@gmail.com"
    if tenancy_store.get_tenant("acme") is None:
        tenancy_store.create_tenant(id="acme", name="Acme")
    existing, _ = user_store.create_user("Existing Person", email=email, tenant_id="acme")
    _enable_oidc(monkeypatch, email, allowed_email_domains=["acme.com"])
    sessions_before = set(auth._SESSIONS)

    response = _callback_with_fresh_flow(client)

    assert response.status_code == 403
    assert response.json()["detail"] == "email domain not allowed"
    assert set(auth._SESSIONS) == sessions_before
    assert user_store.get_by_email("acme", email).id == existing.id


def test_oidc_callback_reuses_existing_email_user_without_duplicate_create(client, monkeypatch):
    email = "existing.person@example.com"
    if tenancy_store.get_tenant("acme") is None:
        tenancy_store.create_tenant(id="acme", name="Acme")
    existing, _ = user_store.create_user("Existing Person", email=email, tenant_id="acme")
    _enable_oidc(monkeypatch, email)

    login = client.get("/admin/oidc/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

    response = client.get(
        "/admin/oidc/callback",
        params={"code": "good-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 302
    user = _session_user_from_redirect(response.headers["location"])
    assert user.id == existing.id
    assert user_store.get_by_email("acme", email).id == existing.id


def test_password_login_still_works_when_oidc_is_enabled(client, monkeypatch):
    _enable_oidc(monkeypatch, "person@example.com")
    user = user_store.create_web_user(
        "admin.oidc@example.com",
        "Admin OIDC",
        password_hash=auth.hash_password("pw"),
        role="admin",
    )

    response = client.post("/admin/login", json={"email": user.email, "password": "pw"})

    assert response.status_code == 200
    assert auth.validate_session(response.json()["token"], idle_timeout=300) == user.id


def test_oidc_disabled_keeps_password_login_behavior(client):
    user = user_store.create_web_user(
        "password.only@example.com",
        "Password Only",
        password_hash=auth.hash_password("pw"),
        role="admin",
    )

    assert client.get("/admin/oidc/login", follow_redirects=False).status_code == 404
    response = client.post("/admin/login", json={"email": user.email, "password": "pw"})
    assert response.status_code == 200
    assert auth.validate_session(response.json()["token"], idle_timeout=300) == user.id


def test_oidc_callback_rejects_unverified_email_without_session_or_user(client, monkeypatch):
    email = "unverified.person@example.com"
    if tenancy_store.get_tenant("acme") is None:
        tenancy_store.create_tenant(id="acme", name="Acme")
    monkeypatch.setattr(
        api,
        "_oidc_settings",
        lambda: OidcSettings(
            enabled=True,
            issuer="https://idp.example.com/realms/acme",
            client_id="fleetent-web",
            redirect_uri="https://fleetent.example.com/admin/oidc/callback",
            tenant="acme",
        ),
    )

    class _UnverifiedOidcRelyingParty:
        def __init__(self, settings: OidcSettings) -> None:
            self.settings = settings

        def build_authorize_url(self, *, state: str, nonce: str) -> str:
            return (
                "https://idp.example.com/oauth2/authorize"
                f"?state={state}&nonce={nonce}&redirect_uri={self.settings.redirect_uri}"
            )

        def exchange_code(
            self,
            *,
            code: str,
            state: str,
            expected_state: str,
            nonce: str,
            expected_nonce: str,
        ) -> OidcIdentity:
            assert code == "good-code"
            assert state == expected_state
            assert nonce == expected_nonce
            return OidcIdentity(
                email=email,
                claims={"sub": "oidc-user", "email": email, "email_verified": False},
            )

    monkeypatch.setattr(api, "OidcRelyingParty", _UnverifiedOidcRelyingParty)

    login = client.get("/admin/oidc/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

    response = client.get(
        "/admin/oidc/callback",
        params={"code": "good-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert user_store.get_by_email("acme", email) is None
