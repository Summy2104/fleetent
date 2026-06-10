"""Tests for LocalBearerAdapter (task 1.3).

The adapter resolves legacy users.api_key values to Principal — no platform import.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_user(user_id: str = "u1", tenant_id: str = "t1", status: str = "active"):
    from fleetent.user_store import User

    return User(
        id=user_id,
        name="Alice",
        api_key="ma-abc",
        created_at="2026-01-01",
        tenant_id=tenant_id,
        status=status,
    )


def test_local_bearer_resolves_valid_key():
    from fleetent.identity import LocalBearerAdapter, Principal

    user = _make_user()
    adapter = LocalBearerAdapter()
    with patch("fleetent.identity._legacy_key_lookup", return_value=user):
        result = adapter("ma-validtoken")

    assert result == Principal(user_id="u1", tenant_id="t1")


def test_local_bearer_returns_none_for_missing_key():
    from fleetent.identity import LocalBearerAdapter

    adapter = LocalBearerAdapter()
    with patch("fleetent.identity._legacy_key_lookup", return_value=None):
        assert adapter("ma-badtoken") is None


def test_local_bearer_returns_none_for_blocked_user():
    from fleetent.identity import LocalBearerAdapter

    user = _make_user(status="blocked")
    adapter = LocalBearerAdapter()
    with patch("fleetent.identity._legacy_key_lookup", return_value=user):
        assert adapter("ma-blockedkey") is None


def test_local_bearer_does_not_import_platform():
    """LocalBearerAdapter's resolve path must not touch fleetent.platform.*."""
    import sys

    # Remove any previously cached platform submodules to get a clean check.
    platform_mods = [k for k in sys.modules if k.startswith("fleetent.platform")]
    for mod in platform_mods:
        sys.modules.pop(mod, None)

    from fleetent.identity import LocalBearerAdapter

    adapter = LocalBearerAdapter()
    with patch("fleetent.identity._legacy_key_lookup", return_value=None):
        adapter("ma-anytoken")

    loaded = [k for k in sys.modules if k.startswith("fleetent.platform")]
    assert loaded == [], f"platform modules loaded during LocalBearerAdapter.resolve: {loaded}"
