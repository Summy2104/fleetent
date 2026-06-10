"""Guard: the 4 migrated management store modules must not self-build their tables.

After onboarding api_keys / audit_log / im_connectors / im_channel_allowlist into
alembic, their store modules must no longer contain CREATE TABLE statements for
those tables.  Schema is alembic's responsibility; stores are CRUD-only.
"""

from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"


def _read(rel: str) -> str:
    return (_SRC / rel).read_text()


def test_api_key_store_no_create_table():
    src = _read("fleetent/platform/user_management/api_key_store.py")
    assert "CREATE TABLE" not in src, "api_key_store must not contain CREATE TABLE"


def test_audit_log_no_create_table():
    src = _read("fleetent/audit_log.py")
    assert "CREATE TABLE" not in src, "audit_log must not contain CREATE TABLE"


def test_connector_store_no_create_table():
    src = _read("fleetent/platform/im_gateway_management/connector_store.py")
    assert "CREATE TABLE" not in src, "connector_store must not contain CREATE TABLE"


def test_channel_allowlist_no_create_table():
    src = _read("fleetent/platform/im_gateway_management/channel_allowlist.py")
    assert "CREATE TABLE" not in src, "channel_allowlist must not contain CREATE TABLE"
