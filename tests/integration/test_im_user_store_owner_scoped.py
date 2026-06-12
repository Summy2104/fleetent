"""Owner-keyed IM identity mapping."""

import pytest

from fleetent.platform.im_gateway_management import identity as im_user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "users.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{p}")
    apply_migrations(p)
    return p


def test_same_platform_user_reuses_internal_user_across_owners(db):
    a = im_user_store.get_or_create("ownerA", "slack", "U1")
    b = im_user_store.get_or_create("ownerB", "slack", "U1")
    assert a.id == b.id
    owners = {(row["owner_id"], row["user_id"]) for row in im_user_store.list_all()}
    assert owners == {("ownerA", a.id), ("ownerB", a.id)}


def test_get_or_create_idempotent_per_owner(db):
    a1 = im_user_store.get_or_create("ownerA", "slack", "U1")
    a2 = im_user_store.get_or_create("ownerA", "slack", "U1")
    assert a1.id == a2.id


def test_list_all_includes_owner(db):
    im_user_store.get_or_create("ownerA", "slack", "U1")
    rows = im_user_store.list_all()
    assert rows and rows[0]["owner_id"] == "ownerA"


def test_block_isolated_per_owner(db):
    a = im_user_store.get_or_create("ownerA", "slack", "U1")
    im_user_store.get_or_create("ownerB", "slack", "U1")
    # block owner A's identity row
    a_row = next(r for r in im_user_store.list_all() if r["owner_id"] == "ownerA")
    im_user_store.block_user(a_row["id"])
    assert im_user_store.check_allowed_by_user_id(a.id) is False
    b_row = next(r for r in im_user_store.list_all() if r["owner_id"] == "ownerB")
    assert b_row["allowed"] is True
