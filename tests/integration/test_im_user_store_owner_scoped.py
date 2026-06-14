"""Global IM identity mapping no longer scopes rows by owner."""

import pytest

from fleetent.platform.im_gateway_management import identity as im_user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "users.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{p}")
    apply_migrations(p)
    return p


def test_same_platform_user_has_single_global_mapping(db):
    a = im_user_store.get_or_create("slack", "U1", "default")
    b = im_user_store.get_or_create("slack", "U1", "default")
    assert a.id == b.id

    rows = im_user_store.list_all()
    assert len(rows) == 1
    assert rows[0]["platform"] == "slack"
    assert rows[0]["platform_user_id"] == "U1"
    assert rows[0]["user_id"] == a.id


def test_list_all_exposes_user_status_not_owner(db):
    user = im_user_store.get_or_create("slack", "U1", "default")
    row = im_user_store.list_all()[0]
    assert "owner_id" not in row
    assert row["user_id"] == user.id
    assert row["status"] == "active"


def test_block_updates_shared_user_status(db):
    user = im_user_store.get_or_create("slack", "U1", "default")
    row = im_user_store.list_all()[0]
    im_user_store.block_im_user(row["id"])
    assert im_user_store.check_allowed_by_user_id(user.id) is False
    assert im_user_store.list_all()[0]["status"] == "blocked"
