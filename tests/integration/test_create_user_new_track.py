"""Integration + unit: create_user new-track behaviour (task 2.1).

After retire-legacy-api-key-and-agent-rename:
  - create_user returns (User, plaintext_key) tuple
  - api_keys table gains a hashed row (scope ["*"])
  - users table row has no api_key column / value
"""

from __future__ import annotations

import hashlib

import pytest

from tests.integration._migration_template import apply_migrations


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db = tmp_path / "mgmt.db"
    apply_migrations(db)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")


def test_create_user_returns_tuple():
    from fleetent import user_store

    result = user_store.create_user("Alice")
    # Must return a (User, str) tuple — fails while create_user returns just User.
    assert isinstance(result, tuple), f"expected tuple, got {type(result)}"
    user, plaintext = result
    assert user.name == "Alice"
    assert plaintext.startswith("ma-")


def test_create_user_api_keys_has_hashed_row():
    from fleetent import user_store

    result = user_store.create_user("Bob")
    user, plaintext = result
    expected_hash = hashlib.sha256(plaintext.encode()).hexdigest()

    import sqlalchemy as sa

    db_url = f"sqlite:///{__import__('os').environ['DATABASE_URL'].replace('sqlite:///', '')}"
    engine = sa.create_engine(db_url)
    with engine.connect() as c:
        rows = c.execute(
            sa.text("SELECT key_hash, scope FROM api_keys WHERE user_id = :uid"),
            {"uid": user.id},
        ).fetchall()
    engine.dispose()

    assert len(rows) == 1
    assert rows[0][0] == expected_hash
    assert rows[0][1] == '["*"]'


def test_users_row_has_no_api_key_value():
    """users table must not have an api_key column at head migration."""
    import os

    import sqlalchemy as sa

    from fleetent import user_store

    user_store.create_user("Carol")  # just to ensure a row exists

    db_path = os.environ["DATABASE_URL"].replace("sqlite:///", "")
    engine = sa.create_engine(f"sqlite:///{db_path}")
    inspector = sa.inspect(engine)
    col_names = {c["name"] for c in inspector.get_columns("users")}
    engine.dispose()

    assert "api_key" not in col_names
