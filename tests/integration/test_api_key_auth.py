import pytest

import fleetent.platform.user_management as user_management
import fleetent.platform.user_management.api_key_store as aks
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    # Wire the platform api_keys resolver so authenticate checks the api_keys table in
    # this test context, matching production platform behaviour.
    monkeypatch.setattr(user_store, "_api_key_resolver", aks.resolve)
    return tmp_path / "users.db"


def test_authenticate_via_api_keys(db):
    u = user_store.create_user("Alice")
    plaintext, meta = aks.issue_key(u.id, scope=["ops-bot"])
    result = user_store.authenticate(plaintext)
    assert result is not None
    user, key_meta = result
    assert user.id == u.id
    assert key_meta["scope"] == ["ops-bot"]


def test_authenticate_blocked_user_rejected(db):
    u = user_store.create_user("Bob")
    plaintext, _ = aks.issue_key(u.id)
    user_store.set_status(u.id, "blocked")
    assert user_store.authenticate(plaintext) is None


def test_authenticate_revoked_key_rejected(db):
    u = user_store.create_user("Cara")
    plaintext, meta = aks.issue_key(u.id)
    aks.revoke_key(meta["id"])
    assert user_store.authenticate(plaintext) is None


def test_authenticate_legacy_single_column_key(db):
    # create_user writes the legacy users.api_key column; authenticate should still work
    u = user_store.create_user("Dan")
    result = user_store.authenticate(u.api_key)
    assert result is not None
    user, key_meta = result
    assert user.id == u.id
    assert key_meta["scope"] == ["*"]


def test_migrate_api_keys_moves_legacy(db):
    u = user_store.create_user("Eve")
    moved = user_management.migrate_api_keys()
    assert u.id in moved
    keys = aks.list_keys(u.id)
    assert len(keys) == 1
    assert keys[0]["scope"] == ["*"]
    # migration is idempotent
    assert user_management.migrate_api_keys() == []


def test_get_by_api_key_still_works(db):
    u = user_store.create_user("Frank")
    plaintext, _ = aks.issue_key(u.id)
    assert user_store.get_by_api_key(plaintext).id == u.id
