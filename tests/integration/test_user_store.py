import pytest

import fleetent.im_user_store as im_user_store
import fleetent.platform.im_gateway_management.im_channel_allowlist as im_channel_allowlist
import fleetent.platform.im_gateway_management.im_connector_store as im_connector_store
import fleetent.platform.user_management.api_key_store as api_key_store
import fleetent.platform.user_management.invite_store as invite_store
from fleetent import paths, user_store
from fleetent.governance import audit_log, blocklist, permission_gate, quota

DEFAULT_USER_STORE_DB_PATH = user_store.DB_PATH
DEFAULT_LEGACY_RE_EXPORT_DB_PATHS = {
    "api_key_store": api_key_store.DB_PATH,
    "audit_log": audit_log.DB_PATH,
    "blocklist": blocklist.DB_PATH,
    "im_channel_allowlist": im_channel_allowlist.DB_PATH,
    "im_connector_store": im_connector_store.DB_PATH,
    "im_user_store": im_user_store.DB_PATH,
    "invite_store": invite_store.DB_PATH,
    "permission_gate": permission_gate.DB_PATH,
    "quota": quota.DB_PATH,
}


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")


def test_create_user_returns_user():
    user = user_store.create_user("Alice")
    assert user.name == "Alice"
    assert user.api_key.startswith("ma-")
    assert len(user.id) == 36  # uuid4


def test_default_db_path_uses_fleetent_database():
    assert paths.data_dir() / "fleetent.db" == DEFAULT_USER_STORE_DB_PATH


def test_legacy_re_exports_inherit_default_db_path():
    assert DEFAULT_LEGACY_RE_EXPORT_DB_PATHS
    for db_path in DEFAULT_LEGACY_RE_EXPORT_DB_PATHS.values():
        assert db_path == paths.data_dir() / "fleetent.db"


def test_get_by_api_key_found():
    user = user_store.create_user("Bob")
    found = user_store.get_by_api_key(user.api_key)
    assert found is not None
    assert found.id == user.id


def test_get_by_api_key_not_found():
    assert user_store.get_by_api_key("ma-doesnotexist") is None


def test_get_by_id_found():
    user = user_store.create_user("Carol")
    found = user_store.get_by_id(user.id)
    assert found is not None
    assert found.name == "Carol"


def test_get_by_id_not_found():
    assert user_store.get_by_id("00000000-0000-0000-0000-000000000000") is None


def test_list_users_returns_all():
    user_store.create_user("Dave")
    user_store.create_user("Eve")
    users = user_store.list_users()
    names = [u.name for u in users]
    assert "Dave" in names and "Eve" in names


def test_rotate_key_changes_api_key():
    user = user_store.create_user("Frank")
    old_key = user.api_key
    updated = user_store.rotate_key(user.id)
    assert updated.api_key != old_key
    assert updated.api_key.startswith("ma-")
    assert user_store.get_by_api_key(old_key) is None
    assert user_store.get_by_api_key(updated.api_key) is not None
