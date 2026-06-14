import sqlite3
from contextlib import contextmanager

import pytest

from fleetent import user_store
from fleetent.platform.im_gateway_management import identity as im_user_store
from fleetent.platform.tenancy import store as tenancy_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_get_or_create_provisions_edge_tenant_and_reuses_platform_identity(db):
    tenancy_store.create_tenant(id="tenant-a", name="Tenant A")
    tenancy_store.create_tenant(id="tenant-b", name="Tenant B")

    user1 = im_user_store.get_or_create("slack", "U123", "tenant-a")
    user2 = im_user_store.get_or_create("slack", "U123", "tenant-b")

    assert user1.id == user2.id
    assert user1.tenant_id == "tenant-a"

    conn = sqlite3.connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM im_users WHERE platform='slack' AND platform_user_id='U123'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_get_or_create_new_user(db):
    user = im_user_store.get_or_create("slack", "U123", "default")
    assert user.id is not None
    assert user.name == "slack:U123"


def test_get_or_create_returns_same_user(db):
    user1 = im_user_store.get_or_create("slack", "U123", "default")
    user2 = im_user_store.get_or_create("slack", "U123", "default")
    assert user1.id == user2.id


def test_different_platforms_different_users(db):
    slack_user = im_user_store.get_or_create("slack", "U123", "default")
    tg_user = im_user_store.get_or_create("telegram", "U123", "default")
    assert slack_user.id != tg_user.id


def test_rebind_im_identity_to_existing_user(db):
    slack_user = im_user_store.get_or_create("slack", "U1", "default")
    target = im_user_store.get_or_create("telegram", "T1", "default")
    im_id = im_user_store.list_im_identities(slack_user.id)[0]["id"]

    im_user_store.rebind_im_identity(im_id, target.id)

    assert im_user_store.list_im_identities(slack_user.id) == []
    platforms = {i["platform"] for i in im_user_store.list_im_identities(target.id)}
    assert platforms == {"slack", "telegram"}
    assert user_store.get_by_id(slack_user.id) is not None


def test_rebind_unknown_target_raises(db):
    u = im_user_store.get_or_create("slack", "U2", "default")
    im_id = im_user_store.list_im_identities(u.id)[0]["id"]
    with pytest.raises(ValueError):
        im_user_store.rebind_im_identity(im_id, "ghost-user-id")


def test_rebind_unknown_identity_raises(db):
    target = im_user_store.get_or_create("slack", "U3", "default")
    with pytest.raises(ValueError):
        im_user_store.rebind_im_identity(999999, target.id)


def test_unique_constraint(db):
    im_user_store.get_or_create("slack", "U123", "default")
    im_user_store.get_or_create("slack", "U123", "default")
    conn = sqlite3.connect(db)
    count = conn.execute(
        "SELECT COUNT(*) FROM im_users WHERE platform='slack' AND platform_user_id='U123'"
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_check_allowed_tracks_blocked_status(db):
    user = im_user_store.get_or_create("slack", "UB1", "default")
    assert im_user_store.check_allowed_by_user_id(user.id) is True
    im_id = im_user_store.list_im_identities(user.id)[0]["id"]
    im_user_store.block_im_user(im_id, reason="spam", actor="admin1")
    assert im_user_store.check_allowed_by_user_id(user.id) is False
    im_user_store.restore_im_user(im_id, reason="appealed", actor="admin1")
    assert im_user_store.check_allowed_by_user_id(user.id) is True


def test_list_pending_empty(db):
    assert im_user_store.list_pending() == []


def test_identity_crud_works_on_alembic_schema_without_runtime_schema_checks(db, monkeypatch):
    executed_sql: list[str] = []

    @contextmanager
    def traced_conn():
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        conn.set_trace_callback(executed_sql.append)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    monkeypatch.setattr(im_user_store, "_conn", traced_conn)

    user = im_user_store.get_or_create("slack", "U777", "default")
    im_id = im_user_store.list_im_identities(user.id)[0]["id"]
    im_user_store.block_im_user(im_id)
    assert im_user_store.check_allowed_by_user_id(user.id) is False
    assert len(im_user_store.list_all()) == 1
    assert im_user_store.list_pending() == []
    im_user_store.restore_im_user(im_id)
    assert im_user_store.check_allowed_by_user_id(user.id) is True

    schema_sql = [
        statement
        for statement in executed_sql
        if "CREATE TABLE" in statement
        or "ALTER TABLE" in statement
        or "sqlite_master" in statement
        or "PRAGMA table_info" in statement
    ]
    assert schema_sql == []
