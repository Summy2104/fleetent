"""Unit tests for TUI token-based authentication in standalone agent.

Tests the _validate_tui_token() helper that guards the /ws endpoint,
avoiding TestClient (not allowed in unit layer per CLAUDE.md).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fleetent.identity import Principal


def test_validate_tui_token_accepts_matching_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", "ma-test-token-12345")
    from fleetent.identity import Principal
    from fleetent.runtime.agent_app import _validate_tui_token

    result = _validate_tui_token("Bearer ma-test-token-12345")
    assert isinstance(result, Principal)
    assert result.user_id == "local"


def test_validate_tui_token_rejects_wrong_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", "ma-correct-token")
    from fleetent.runtime.agent_app import _validate_tui_token

    assert _validate_tui_token("Bearer ma-wrong-token") is None


def test_validate_tui_token_rejects_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FLEETENT_TUI_TOKEN", raising=False)
    from fleetent.runtime.agent_app import _validate_tui_token

    assert _validate_tui_token("Bearer ma-anything") is None


def test_validate_tui_token_rejects_missing_bearer_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", "ma-token")
    from fleetent.runtime.agent_app import _validate_tui_token

    assert _validate_tui_token("ma-token") is None


def test_resolve_ingress_principal_prefers_carried_principal_after_transport_auth() -> None:
    from fleetent.identity import encode_ingress_principal
    from fleetent.runtime.agent_app import _resolve_ingress_principal

    token_principal = Principal(user_id="gateway-token", tenant_id="default")
    carried_principal = Principal(user_id="operator-1", tenant_id="tenant-1")

    result = _resolve_ingress_principal(
        "Bearer ma-valid-token",
        encode_ingress_principal(carried_principal),
        local_bearer=lambda token: token_principal,
    )

    assert result == carried_principal


def test_resolve_ingress_principal_falls_back_to_transport_principal_when_header_absent() -> None:
    from fleetent.runtime.agent_app import _resolve_ingress_principal

    token_principal = Principal(user_id="gateway-token", tenant_id="default")

    result = _resolve_ingress_principal(
        "Bearer ma-valid-token",
        None,
        local_bearer=lambda token: token_principal,
    )

    assert result == token_principal


def test_resolve_ingress_principal_rejects_forged_header_without_valid_transport_token() -> None:
    from fleetent.identity import encode_ingress_principal
    from fleetent.runtime.agent_app import _resolve_ingress_principal

    with pytest.raises(HTTPException, match="invalid or missing bearer token") as excinfo:
        _resolve_ingress_principal(
            "",
            encode_ingress_principal(Principal(user_id="forged-user", tenant_id="tenant-1")),
            local_bearer=lambda token: None,
        )

    assert excinfo.value.status_code == 401


def test_resolve_ingress_principal_keeps_tenant_guard_for_carried_principal() -> None:
    from fleetent.identity import encode_ingress_principal
    from fleetent.runtime.agent_app import _check_tenant, _resolve_ingress_principal

    carried = _resolve_ingress_principal(
        "Bearer ma-valid-token",
        encode_ingress_principal(Principal(user_id="operator-1", tenant_id="tenant-2")),
        local_bearer=lambda token: Principal(user_id="gateway-token", tenant_id="default"),
    )

    assert _check_tenant(carried, "tenant-1") is False
