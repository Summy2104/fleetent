from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from fleetent import agent_store, connectors
from fleetent.platform.connector_management import vault_provider


@pytest.fixture
def credential_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_put(
        user_id: str,
        service_id: str,
        payload: dict[str, object],
        *,
        updated_by: str,
        status: str,
    ) -> None:
        calls.append(
            {
                "user_id": user_id,
                "service_id": service_id,
                "payload": payload,
                "updated_by": updated_by,
                "status": status,
            }
        )

    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "put_oauth_credential",
        fake_put,
    )
    return calls


def test_expires_at_and_is_expired_cover_valid_invalid_and_boundary() -> None:
    future = datetime.now(UTC) + timedelta(minutes=1)
    past = datetime.now(UTC) - timedelta(minutes=1)
    now = datetime.now(UTC)

    assert vault_provider._expires_at({"expires_at": future.isoformat()}) == future
    assert vault_provider._expires_at({"expires_at": ""}) is None
    assert vault_provider._expires_at({"expires_at": "not-a-date"}) is None
    assert vault_provider._expires_at({}) is None

    assert vault_provider._is_expired({"expires_at": past.isoformat()}) is True
    assert vault_provider._is_expired({"expires_at": future.isoformat()}) is False
    assert vault_provider._is_expired({"expires_at": now.isoformat()}) is True
    assert vault_provider._is_expired({}) is False


def test_resolve_principal_returns_agent_service_principal_for_run_as_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vault_provider.agent_store,
        "get_by_name",
        lambda name: agent_store.Agent(
            id=7,
            name=name,
            system_prompt="",
            allowed_tools=[],
            features={},
            plugins=[],
            allowed_skills=[],
            tenant_id="tenant",
            team_id="team",
            skills_dir="skills",
            mcp_server_ids=[],
            model_overrides={},
            memory_namespace="ops",
        ),
    )
    monkeypatch.setattr(
        vault_provider.agent_service_grant_store,
        "list_services_for_agent",
        lambda agent_id: [{"service_id": "slack", "run_as": "agent"}],
    )
    monkeypatch.setattr(
        vault_provider.user_store,
        "get_or_create_service_principal",
        lambda agent_id: f"agent:{agent_id}",
    )

    assert vault_provider._resolve_principal("user-1", "slack", "ops") == "agent:7"


def test_resolve_principal_keeps_caller_for_user_grant_missing_grant_or_missing_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vault_provider.agent_store, "get_by_name", lambda name: None)
    assert vault_provider._resolve_principal("user-1", "slack", "ops") == "user-1"
    assert vault_provider._resolve_principal("user-1", "slack", None) == "user-1"

    monkeypatch.setattr(
        vault_provider.agent_store,
        "get_by_name",
        lambda name: agent_store.Agent(
            id=9,
            name=name,
            system_prompt="",
            allowed_tools=[],
            features={},
            plugins=[],
            allowed_skills=[],
            tenant_id="tenant",
            team_id="team",
            skills_dir="skills",
            mcp_server_ids=[],
            model_overrides={},
            memory_namespace="ops",
        ),
    )
    monkeypatch.setattr(
        vault_provider.agent_service_grant_store,
        "list_services_for_agent",
        lambda agent_id: [{"service_id": "slack", "run_as": "user"}],
    )
    assert vault_provider._resolve_principal("user-1", "slack", "ops") == "user-1"
    assert vault_provider._resolve_principal("user-1", "github", "ops") == "user-1"


def test_get_apikey_credential_returns_credential_when_authorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: {
            "status": "authorized",
            "payload": {"api_key": "secret"},
        },
    )

    result = vault_provider._get_apikey_credential("user-1", "github")

    assert result == connectors.Credential("github", {"api_key": "secret"})


@pytest.mark.parametrize("credential", [None, {"status": "needs_reauth", "payload": {}}])
def test_get_apikey_credential_returns_submit_needs_consent_when_missing_or_not_authorized(
    monkeypatch: pytest.MonkeyPatch,
    credential: dict[str, object] | None,
) -> None:
    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: credential,
    )

    result = vault_provider._get_apikey_credential("user-1", "github")

    assert result == connectors.NeedsConsent(
        connector="github",
        consent_url="/admin/connectors/github/credentials",
    )


@respx.mock
def test_refresh_tokens_success_merges_new_payload_and_preserves_refresh_token(
    monkeypatch: pytest.MonkeyPatch,
    credential_calls: list[dict[str, object]],
) -> None:
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {
            "oauth_config": {
                "token": "https://auth.example/token",
                "client_id": "client-1",
            }
        },
    )
    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: {
            "status": "authorized",
            "payload": {
                "access_token": "new-token",
                "refresh_token": "keep-me",
                "expires_in": 3600,
            },
        },
    )
    route = respx.post("https://auth.example/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "new-token", "expires_in": 3600},
        )
    )

    result = vault_provider._refresh_tokens(
        "user-1",
        "google-drive",
        {
            "payload": {
                "access_token": "old-token",
                "refresh_token": "keep-me",
            }
        },
        ["drive.readonly"],
    )

    assert isinstance(result, connectors.Credential)
    assert result.connector == "google-drive"
    assert result.client["access_token"] == "new-token"
    assert result.client["refresh_token"] == "keep-me"
    assert result.client["scopes"] == ["drive.readonly"]
    assert route.called is True
    assert route.calls.last.request.content.decode() == (
        "grant_type=refresh_token&refresh_token=keep-me&client_id=client-1&scope=drive.readonly"
    )
    assert credential_calls == [
        {
            "user_id": "user-1",
            "service_id": "google-drive",
            "payload": {
                "access_token": "new-token",
                "refresh_token": "keep-me",
                "expires_in": 3600,
                "scopes": ["drive.readonly"],
            },
            "updated_by": "user-1",
            "status": "authorized",
        }
    ]


@respx.mock
def test_refresh_tokens_invalid_grant_marks_needs_reauth(
    monkeypatch: pytest.MonkeyPatch,
    credential_calls: list[dict[str, object]],
) -> None:
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {"oauth_config": {"token": "https://auth.example/token"}},
    )
    respx.post("https://auth.example/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )

    result = vault_provider._refresh_tokens(
        "user-1",
        "google-drive",
        {"payload": {"refresh_token": "stale-refresh"}},
        ["drive.readonly"],
    )

    assert result == connectors.NeedsConsent(
        connector="google-drive",
        consent_url="/admin/connectors/authorize/google-drive?user_id=user-1",
    )
    assert credential_calls == [
        {
            "user_id": "user-1",
            "service_id": "google-drive",
            "payload": {"refresh_token": "stale-refresh"},
            "updated_by": "user-1",
            "status": "needs_reauth",
        }
    ]


@respx.mock
def test_refresh_tokens_network_failure_marks_error(
    monkeypatch: pytest.MonkeyPatch,
    credential_calls: list[dict[str, object]],
) -> None:
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {"oauth_config": {"token": "https://auth.example/token"}},
    )
    respx.post("https://auth.example/token").mock(side_effect=httpx.ConnectError("boom"))

    result = vault_provider._refresh_tokens(
        "user-1",
        "google-drive",
        {"payload": {"refresh_token": "stale-refresh"}},
        ["drive.readonly"],
    )

    assert result == connectors.CredentialError(
        connector="google-drive",
        message="credential refresh failed",
        retryable=True,
    )
    assert credential_calls == [
        {
            "user_id": "user-1",
            "service_id": "google-drive",
            "payload": {"refresh_token": "stale-refresh"},
            "updated_by": "user-1",
            "status": "error",
        }
    ]


@respx.mock
def test_refresh_tokens_http_failure_marks_error(
    monkeypatch: pytest.MonkeyPatch,
    credential_calls: list[dict[str, object]],
) -> None:
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {"oauth_config": {"token": "https://auth.example/token"}},
    )
    respx.post("https://auth.example/token").mock(return_value=httpx.Response(503))

    result = vault_provider._refresh_tokens(
        "user-1",
        "google-drive",
        {"payload": {"refresh_token": "stale-refresh"}},
        ["drive.readonly"],
    )

    assert result == connectors.CredentialError(
        connector="google-drive",
        message="credential refresh failed",
        retryable=True,
    )
    assert credential_calls == [
        {
            "user_id": "user-1",
            "service_id": "google-drive",
            "payload": {"refresh_token": "stale-refresh"},
            "updated_by": "user-1",
            "status": "error",
        }
    ]


def test_get_credential_returns_apikey_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {"protocol": "apikey"},
    )
    monkeypatch.setattr(
        vault_provider,
        "_get_apikey_credential",
        lambda user_id, service_id: connectors.Credential(service_id, {"api_key": "secret"}),
    )

    result = vault_provider.get_credential("user-1", "github", ["repo"])

    assert result == connectors.Credential("github", {"api_key": "secret"})


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        (
            {"protocol": "apikey", "enabled": False},
            connectors.NeedsConsent(
                connector="github",
                consent_url="/admin/connectors/github/credentials",
            ),
        ),
        (
            {"protocol": "oauth", "enabled": False},
            connectors.NeedsConsent(
                connector="github",
                consent_url="/admin/connectors/authorize/github?user_id=user-1",
            ),
        ),
    ],
)
def test_get_credential_returns_needs_consent_when_service_disabled(
    monkeypatch: pytest.MonkeyPatch,
    service: dict[str, object],
    expected: connectors.NeedsConsent,
) -> None:
    monkeypatch.setattr(
        vault_provider, "_resolve_principal", lambda user_id, service_id, agent: user_id
    )
    monkeypatch.setattr(vault_provider.external_service_store, "get_service", lambda service_id: service)
    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: {"status": "authorized", "payload": {"access_token": "ok"}},
    )
    monkeypatch.setattr(vault_provider, "_get_apikey_credential", lambda *args: pytest.fail("disabled service should not resolve apikey credentials"))
    monkeypatch.setattr(vault_provider, "_is_expired", lambda payload: pytest.fail("disabled service should not inspect oauth expiry"))

    result = vault_provider.get_credential("user-1", "github", ["repo"])

    assert result == expected


def test_get_credential_returns_needs_consent_for_missing_and_needs_reauth_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vault_provider, "_resolve_principal", lambda user_id, service_id, agent: user_id
    )
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {"protocol": "oauth"},
    )

    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: None,
    )
    missing = vault_provider.get_credential("user-1", "github", ["repo"])
    assert missing == connectors.NeedsConsent(
        connector="github",
        consent_url="/admin/connectors/authorize/github?user_id=user-1",
    )

    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: {"status": "needs_reauth", "payload": {}},
    )
    needs_reauth = vault_provider.get_credential("user-1", "github", ["repo"])
    assert needs_reauth == connectors.NeedsConsent(
        connector="github",
        consent_url="/admin/connectors/authorize/github?user_id=user-1",
    )


def test_get_credential_expired_path_delegates_to_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vault_provider, "_resolve_principal", lambda user_id, service_id, agent: "agent:7"
    )
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {"protocol": "oauth"},
    )
    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: {"status": "authorized", "payload": {"refresh_token": "r1"}},
    )
    monkeypatch.setattr(vault_provider, "_is_expired", lambda payload: True)
    monkeypatch.setattr(
        vault_provider,
        "_refresh_tokens",
        lambda user_id, service_id, credential, scopes: connectors.Credential(
            service_id,
            {"access_token": "fresh", "subject": user_id, "scopes": scopes},
        ),
    )

    result = vault_provider.get_credential("user-1", "github", ["repo"], agent_name="ops")

    assert result == connectors.Credential(
        connector="github",
        client={"access_token": "fresh", "subject": "agent:7", "scopes": ["repo"]},
    )


def test_get_credential_returns_error_for_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vault_provider, "_resolve_principal", lambda user_id, service_id, agent: user_id
    )
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {"protocol": "oauth"},
    )
    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: {"status": "error", "payload": {}},
    )
    monkeypatch.setattr(vault_provider, "_is_expired", lambda payload: False)

    result = vault_provider.get_credential("user-1", "github", ["repo"])

    assert result == connectors.CredentialError(
        connector="github",
        message="credential refresh failed",
        retryable=True,
    )


def test_get_credential_returns_needs_consent_for_unknown_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vault_provider, "_resolve_principal", lambda user_id, service_id, agent: user_id
    )
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {"protocol": "oauth"},
    )
    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: {"status": "pending", "payload": {}},
    )
    monkeypatch.setattr(vault_provider, "_is_expired", lambda payload: False)

    result = vault_provider.get_credential("user-1", "github", ["repo"])

    assert result == connectors.NeedsConsent(
        connector="github",
        consent_url="/admin/connectors/authorize/github?user_id=user-1",
    )


def test_get_credential_returns_authorized_credential_and_defaults_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vault_provider, "_resolve_principal", lambda user_id, service_id, agent: user_id
    )
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {"protocol": "oauth"},
    )
    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: {"status": "authorized", "payload": {"access_token": "ok"}},
    )
    monkeypatch.setattr(vault_provider, "_is_expired", lambda payload: False)

    result = vault_provider.get_credential("user-1", "github", ["repo"])

    assert result == connectors.Credential(
        connector="github",
        client={"access_token": "ok", "scopes": ["repo"]},
    )


def test_get_credential_allows_enabled_authorized_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vault_provider, "_resolve_principal", lambda user_id, service_id, agent: user_id
    )
    monkeypatch.setattr(
        vault_provider.external_service_store,
        "get_service",
        lambda service_id: {"protocol": "oauth", "enabled": True},
    )
    monkeypatch.setattr(
        vault_provider.external_credential_store,
        "get_credential",
        lambda user_id, service_id: {"status": "authorized", "payload": {"access_token": "ok"}},
    )
    monkeypatch.setattr(vault_provider, "_is_expired", lambda payload: False)

    result = vault_provider.get_credential("user-1", "github", ["repo"])

    assert result == connectors.Credential(
        connector="github",
        client={"access_token": "ok", "scopes": ["repo"]},
    )
