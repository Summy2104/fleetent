from __future__ import annotations

import importlib.util

import httpx
import fleetent.user_store as user_store
from fleetent.platform.im_gateway_management import identity as im_identity


def test_oidc_stub_endpoints_and_rp_validation() -> None:
    assert importlib.util.find_spec("tests.e2e._oidc_stub") is not None

    from tests.e2e._identity_helpers import build_oidc_settings, start_oidc_stub

    with start_oidc_stub(email="stub.person@example.com") as stub:
        discovery = stub.client.get(f"{stub.issuer}/.well-known/openid-configuration")
        assert discovery.status_code == 200
        assert discovery.json()["issuer"] == stub.issuer

        authorize = stub.client.get(
            f"{stub.issuer}/oauth/authorize",
            params={
                "client_id": stub.client_id,
                "redirect_uri": "https://fleetent.example.com/admin/oidc/callback",
                "response_type": "code",
                "scope": "openid email",
                "state": "state-123",
                "nonce": "nonce-456",
            },
            follow_redirects=False,
        )
        assert authorize.status_code == 302
        assert "code=" in authorize.headers["location"]
        assert "state=state-123" in authorize.headers["location"]

        code = authorize.headers["location"].split("code=", 1)[1].split("&", 1)[0]
        token = stub.client.post(
            f"{stub.issuer}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "https://fleetent.example.com/admin/oidc/callback",
                "client_id": stub.client_id,
                "client_secret": stub.client_secret,
            },
        )
        assert token.status_code == 200
        assert token.json()["id_token"]

        jwks = stub.client.get(f"{stub.issuer}/oauth/jwks")
        assert jwks.status_code == 200
        assert jwks.json()["keys"]

        identity = stub.relying_party(build_oidc_settings(stub)).exchange_code(
            code=code,
            state="state-123",
            expected_state="state-123",
            nonce="nonce-456",
            expected_nonce="nonce-456",
        )
        assert identity.email == "stub.person@example.com"
        assert identity.claims["nonce"] == "nonce-456"


def test_oidc_login_provisions_user_and_creates_session(
    tmp_path, monkeypatch, llm_stub_base_url: str
) -> None:
    from tests.e2e import _identity_helpers as helpers
    from tests.e2e._identity_helpers import start_managed_identity_stack, start_oidc_stub

    assert hasattr(helpers, "login_via_oidc")

    email = "new.person@example.com"
    with start_oidc_stub(email=email) as stub:
        with start_managed_identity_stack(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            llm_stub_base_url=llm_stub_base_url,
            oidc_stub=stub,
        ) as stack:
            result = helpers.login_via_oidc(platform_url=stack.platform_url)
            me = httpx.get(
                f"{stack.platform_url}/admin/me",
                headers={"Authorization": f"Session {result.token}"},
                timeout=10.0,
            )
            assert me.status_code == 200
            user = user_store.get_by_email("default", email)
            assert user is not None
            assert result.callback.status_code == 302
            assert result.callback.headers["location"].startswith("/admin/ui/login?token=")
            assert user.email == email
            assert user.tenant_id == "default"


def test_oidc_callback_reuses_existing_email_user_without_duplicate_create(
    tmp_path, monkeypatch, llm_stub_base_url: str
) -> None:
    from tests.e2e import _identity_helpers as helpers
    from tests.e2e._identity_helpers import start_managed_identity_stack, start_oidc_stub

    assert hasattr(helpers, "count_users_with_email")

    email = "existing.person@example.com"
    with start_oidc_stub(email=email) as stub:
        with start_managed_identity_stack(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            llm_stub_base_url=llm_stub_base_url,
            oidc_stub=stub,
        ) as stack:
            existing, _ = user_store.create_user("Existing Person", email=email, tenant_id="default")
            result = helpers.login_via_oidc(platform_url=stack.platform_url)
            me = httpx.get(
                f"{stack.platform_url}/admin/me",
                headers={"Authorization": f"Session {result.token}"},
                timeout=10.0,
            )
            assert me.status_code == 200
            user = user_store.get_by_email("default", email)
            assert user is not None
            assert user.id == existing.id
            assert helpers.count_users_with_email("default", email) == 1


def test_link_confirm_binds_identity_rejects_reuse_and_unlinks(
    tmp_path, monkeypatch, llm_stub_base_url: str
) -> None:
    from tests.e2e import _identity_helpers as helpers
    from tests.e2e._identity_helpers import start_managed_identity_stack, start_oidc_stub

    assert hasattr(helpers, "confirm_link_code")

    email = "link.person@example.com"
    with start_oidc_stub(email=email) as stub:
        with start_managed_identity_stack(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            llm_stub_base_url=llm_stub_base_url,
            oidc_stub=stub,
        ) as stack:
            result = helpers.login_via_oidc(platform_url=stack.platform_url)
            current_user = user_store.get_by_email("default", email)
            assert current_user is not None

            initiate = httpx.post(
                f"{stack.platform_url}/admin/link/initiate",
                headers={"Authorization": f"Session {result.token}"},
                timeout=10.0,
            )
            assert initiate.status_code == 200
            link_code = initiate.json()["code"]

            confirm = helpers.confirm_link_code(
                platform_url=stack.platform_url,
                node_id=stack.node_id,
                node_service_key=stack.node_service_key,
                platform="telegram",
                platform_user_id="tg-user-1",
                code=link_code,
            )
            assert confirm.status_code == 200
            assert confirm.json()["user_id"] == current_user.id
            assert im_identity.get_mapped_user("telegram", "tg-user-1").id == current_user.id

            confirm_again = helpers.confirm_link_code(
                platform_url=stack.platform_url,
                node_id=stack.node_id,
                node_service_key=stack.node_service_key,
                platform="telegram",
                platform_user_id="tg-user-1",
                code=link_code,
            )
            assert confirm_again.status_code == 404

            conflicting = im_identity.get_or_create("telegram", "tg-conflict", "default")
            assert conflicting.id != current_user.id

            conflict_initiate = httpx.post(
                f"{stack.platform_url}/admin/link/initiate",
                headers={"Authorization": f"Session {result.token}"},
                timeout=10.0,
            )
            conflict = helpers.confirm_link_code(
                platform_url=stack.platform_url,
                node_id=stack.node_id,
                node_service_key=stack.node_service_key,
                platform="telegram",
                platform_user_id="tg-conflict",
                code=conflict_initiate.json()["code"],
            )
            assert conflict.status_code == 409

            unlink = httpx.post(
                f"{stack.platform_url}/admin/link/unlink",
                headers={"Authorization": f"Session {result.token}"},
                json={"platform": "telegram", "platform_user_id": "tg-user-1"},
                timeout=10.0,
            )
            assert unlink.status_code == 200
            assert im_identity.get_mapped_user("telegram", "tg-user-1") is None
