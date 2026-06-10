"""Tests for Principal dataclass and IdentityPort protocol (tasks 1.1 / 1.2)."""

import pytest


def test_principal_has_user_id_and_tenant_id():
    from fleetent.identity import Principal

    p = Principal(user_id="u1", tenant_id="t1")
    assert p.user_id == "u1"
    assert p.tenant_id == "t1"


def test_principal_is_lean_no_extra_fields():
    """Principal MUST NOT carry role, scopes, display_name, or team."""
    from fleetent.identity import Principal

    p = Principal(user_id="u1", tenant_id="t1")
    assert not hasattr(p, "role")
    assert not hasattr(p, "scopes")
    assert not hasattr(p, "display_name")
    assert not hasattr(p, "team")


def test_principal_equality():
    from fleetent.identity import Principal

    assert Principal("u1", "t1") == Principal("u1", "t1")
    assert Principal("u1", "t1") != Principal("u2", "t1")


def test_principal_is_hashable():
    """frozen dataclass — must be usable as dict key / set element."""
    from fleetent.identity import Principal

    s = {Principal("u1", "t1"), Principal("u2", "t1")}
    assert len(s) == 2


def test_identity_port_protocol_accepts_callable():
    """IdentityPort is a protocol; any callable with the right signature satisfies it."""
    from fleetent.identity import IdentityPort, Principal

    def my_adapter(credentials: str) -> Principal | None:
        return Principal(user_id="u1", tenant_id="default") if credentials == "valid" else None

    # Protocol conformance is structural — just calling it is the test.
    port: IdentityPort = my_adapter  # type: ignore[assignment]
    result = port("valid")
    assert result == Principal("u1", "default")
    assert port("bad") is None


def test_system_principal_exists():
    """SYSTEM_PRINCIPAL sentinel must be available for infrastructure tasks."""
    from fleetent.identity import SYSTEM_PRINCIPAL, Principal

    assert isinstance(SYSTEM_PRINCIPAL, Principal)
    assert SYSTEM_PRINCIPAL.user_id == "system"
