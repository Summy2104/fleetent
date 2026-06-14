import pytest

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
    u, _ = user_store.create_user("Alice")
    plaintext, meta = aks.issue_key(u.id, scope=["ops-bot"])
    result = user_store.authenticate(plaintext)
    assert result is not None
    user, key_meta = result
    assert user.id == u.id
    assert key_meta["scope"] == ["ops-bot"]


def test_authenticate_blocked_user_rejected(db):
    u, _ = user_store.create_user("Bob")
    plaintext, _ = aks.issue_key(u.id)
    user_store.set_status(u.id, "blocked")
    assert user_store.authenticate(plaintext) is None


def test_authenticate_revoked_key_rejected(db):
    u, _ = user_store.create_user("Cara")
    plaintext, meta = aks.issue_key(u.id)
    aks.revoke_key(meta["id"])
    assert user_store.authenticate(plaintext) is None


def test_get_by_api_key_still_works(db):
    u, _ = user_store.create_user("Frank")
    plaintext, _ = aks.issue_key(u.id)
    assert user_store.get_by_api_key(plaintext).id == u.id
