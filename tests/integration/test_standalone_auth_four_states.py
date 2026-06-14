"""Integration: standalone authenticate four-state coverage (task 2.2).

With no resolver injected (standalone form), authenticate must:
  - valid key   → (User, meta) with correct user_id and scope
  - revoked     → None
  - expired     → None
  - blocked user → None

LocalBearerAdapter must return Principal for valid key, None otherwise.
"""

from __future__ import annotations

import datetime

import pytest

import fleetent.platform.user_management.api_key_store as aks
from fleetent import user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "mgmt.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    # Ensure no platform resolver is injected (standalone mode).
    monkeypatch.setattr(user_store, "_api_key_resolver", None)


def _make_user(name: str) -> tuple[user_store.User, str]:
    """Create a user and issue a fresh api_key via api_key_store.issue_key.

    Bypasses the create_user return-type change so 2.2 tests isolate authenticate /
    LocalBearerAdapter behavior (create_user return-type is tested separately in 2.1).
    """
    user = user_store.create_user(name)
    if isinstance(user, tuple):
        user = user[0]  # tolerate when 2.4 lands before these tests run
    # Revoke the key that create_user may have inserted, then issue a fresh known one.
    for key in aks.list_keys(user.id):
        aks.revoke_key(key["id"])
    plaintext, _ = aks.issue_key(user.id, scope=["*"])
    return user, plaintext


def test_valid_key_authenticates():
    user, plaintext = _make_user("Alice")
    result = user_store.authenticate(plaintext)
    assert result is not None
    resolved_user, meta = result
    assert resolved_user.id == user.id
    assert meta["scope"] == ["*"]


def test_revoked_key_rejected():
    user, plaintext = _make_user("Bob")
    keys = [k for k in aks.list_keys(user.id) if k["revoked_at"] is None]
    assert len(keys) == 1
    aks.revoke_key(keys[0]["id"])
    assert user_store.authenticate(plaintext) is None


def test_expired_key_rejected():
    user, plaintext = _make_user("Carol")
    past = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)).isoformat()
    # Revoke the active key and issue an expired one.
    for k in aks.list_keys(user.id):
        if k["revoked_at"] is None:
            aks.revoke_key(k["id"])
    expired_pt, _ = aks.issue_key(user.id, scope=["*"], expires_at=past)
    assert user_store.authenticate(expired_pt) is None


def test_blocked_user_rejected():
    user, plaintext = _make_user("Dan")
    user_store.set_status(user.id, "blocked")
    assert user_store.authenticate(plaintext) is None


def test_local_bearer_adapter_valid_key():
    from fleetent.identity import LocalBearerAdapter, Principal

    user, plaintext = _make_user("Eve")
    result = LocalBearerAdapter()(plaintext)
    assert result == Principal(user_id=user.id, tenant_id=user.tenant_id)


def test_local_bearer_adapter_revoked_key():
    from fleetent.identity import LocalBearerAdapter

    user, plaintext = _make_user("Frank")
    for k in aks.list_keys(user.id):
        if k["revoked_at"] is None:
            aks.revoke_key(k["id"])
    assert LocalBearerAdapter()(plaintext) is None


def test_local_bearer_adapter_blocked_user():
    from fleetent.identity import LocalBearerAdapter

    user, plaintext = _make_user("Grace")
    user_store.set_status(user.id, "blocked")
    assert LocalBearerAdapter()(plaintext) is None
