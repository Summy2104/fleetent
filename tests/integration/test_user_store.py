import pytest

import fleetent.platform.im_gateway_management.connector_store as im_connector_store
import fleetent.platform.user_management.api_key_store as api_key_store
from fleetent import user_store
from fleetent.governance import audit_log
from tests.integration._migration_template import apply_migrations

DEFAULT_USER_STORE_DB_PATH = user_store.DB_PATH
DEFAULT_LEGACY_RE_EXPORT_DB_PATHS = {
    "api_key_store": api_key_store.DB_PATH,
    "audit_log": audit_log.DB_PATH,
    "im_connector_store": im_connector_store.DB_PATH,
}


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "users.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")


def test_create_user_returns_user():
    user, api_key = user_store.create_user("Alice")
    assert user.name == "Alice"
    assert api_key.startswith("ma-")
    assert len(user.id) == 36  # uuid4


def _assert_derivation_in_clean_env(code: str) -> None:
    """Run an import-time derivation assertion in a child interpreter.

    Constants are frozen at import. Comparing an in-process constant against a
    call-time paths.X() is fragile: an ambient FLEETENT_HOME in the developer
    shell freezes a different base than a post-delenv call resolves. A child
    interpreter with FLEETENT_HOME stripped checks constant == derivation under
    one consistent environment.
    """
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "FLEETENT_HOME"}
    subprocess.run([sys.executable, "-c", code], env=env, check=True)


def test_default_db_path_uses_management_database():
    _assert_derivation_in_clean_env(
        "from fleetent import paths, user_store; "
        "assert user_store.DB_PATH == paths.data_dir() / 'management.db', user_store.DB_PATH"
    )


def test_legacy_re_exports_inherit_default_db_path():
    _assert_derivation_in_clean_env(
        "from fleetent import paths; "
        "import fleetent.platform.im_gateway_management.connector_store as c; "
        "import fleetent.platform.user_management.api_key_store as k; "
        "from fleetent.governance import audit_log; "
        "expected = paths.data_dir() / 'management.db'; "
        "mods = [c, k, audit_log]; "
        "bad = [m.__name__ for m in mods if m.DB_PATH != expected]; "
        "assert not bad, bad"
    )


def test_get_by_api_key_found():
    user, api_key = user_store.create_user("Bob")
    found = user_store.get_by_api_key(api_key)
    assert found is not None
    assert found.id == user.id


def test_get_by_api_key_not_found():
    assert user_store.get_by_api_key("ma-doesnotexist") is None


def test_get_by_id_found():
    user, _ = user_store.create_user("Carol")
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
    user, old_key = user_store.create_user("Frank")
    updated, new_key = user_store.rotate_key(user.id)
    assert new_key != old_key
    assert new_key.startswith("ma-")
    assert user_store.get_by_api_key(old_key) is None
    assert user_store.get_by_api_key(new_key) is not None
