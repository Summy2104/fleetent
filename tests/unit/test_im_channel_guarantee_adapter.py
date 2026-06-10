"""Tests for IM channel-guarantee adapter (task 3.1).

Verifies resolve_principal preserves the "native id as user_id, no user_store read"
semantic while wrapping the result as a Principal.
"""

from __future__ import annotations


def test_resolve_principal_returns_principal():
    from fleetent.im_gateway.access import resolve_principal
    from fleetent.identity import Principal

    result = resolve_principal("slack", "U123456", tenant_id="acme")
    assert isinstance(result, Principal)
    assert result.user_id == "U123456"
    assert result.tenant_id == "acme"


def test_resolve_principal_uses_platform_user_id_as_user_id():
    """Native platform id must become user_id — no lookup against user_store."""
    from fleetent.im_gateway.access import resolve_principal
    from fleetent.identity import Principal

    result = resolve_principal("telegram", "987654321", tenant_id="default")
    assert result == Principal(user_id="987654321", tenant_id="default")


def test_resolve_principal_default_tenant():
    """When tenant_id is omitted the adapter falls back to 'default'."""
    from fleetent.im_gateway.access import resolve_principal
    from fleetent.identity import Principal

    result = resolve_principal("slack", "UGUESTID")
    assert result == Principal(user_id="UGUESTID", tenant_id="default")


def test_resolve_principal_does_not_import_platform():
    """resolve_principal must not load any fleetent.platform.* module."""
    import sys

    for key in list(sys.modules):
        if key.startswith("fleetent.platform"):
            del sys.modules[key]

    from fleetent.im_gateway.access import resolve_principal

    resolve_principal("slack", "U1")

    loaded = [k for k in sys.modules if k.startswith("fleetent.platform")]
    assert loaded == [], f"platform modules loaded by resolve_principal: {loaded}"
