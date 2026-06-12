"""onboard im_users current shape into alembic

Revision ID: 079
Revises: 078
Create Date: 2026-06-12

Bring ``im_users`` under full Alembic ownership with the current runtime shape:
``owner_id`` and ``allowed`` columns plus the owner-scoped uniqueness constraint.
Legacy rows are backfilled to the built-in admin owner when present, else the
stable system sentinel.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None

_SYSTEM_OWNER_ID = "__system__"


def _admin_owner_id(bind: sa.Connection) -> str:
    row = bind.execute(sa.text("SELECT id FROM users WHERE role = 'built_in_admin' LIMIT 1")).fetchone()
    return str(row[0]) if row is not None else _SYSTEM_OWNER_ID


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "im_users" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("im_users")}
    if {"owner_id", "allowed", "meta_json"} <= columns:
        return

    owner_id = _admin_owner_id(bind)
    has_meta_json = "meta_json" in columns

    op.execute("ALTER TABLE im_users RENAME TO im_users_legacy_079")
    op.execute(
        """CREATE TABLE im_users (
            id               INTEGER PRIMARY KEY,
            owner_id         TEXT NOT NULL,
            platform         TEXT NOT NULL,
            platform_user_id TEXT NOT NULL,
            user_id          TEXT NOT NULL,
            allowed          BOOLEAN NOT NULL DEFAULT 0,
            created_at       TEXT NOT NULL,
            meta_json        TEXT,
            UNIQUE(owner_id, platform, platform_user_id)
        )"""
    )
    bind.execute(
        sa.text(
            "INSERT INTO im_users "
            "(id, owner_id, platform, platform_user_id, user_id, allowed, created_at, meta_json) "
            "SELECT id, :owner_id, platform, platform_user_id, user_id, 1, created_at, "
            + ("meta_json " if has_meta_json else "NULL ")
            + "FROM im_users_legacy_079"
        ),
        {"owner_id": owner_id},
    )
    op.execute("DROP TABLE im_users_legacy_079")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "im_users" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("im_users")}
    if "owner_id" not in columns and "allowed" not in columns:
        return

    op.execute("ALTER TABLE im_users RENAME TO im_users_current_079")
    op.execute(
        """CREATE TABLE im_users (
            id               INTEGER PRIMARY KEY,
            platform         TEXT NOT NULL,
            platform_user_id TEXT NOT NULL,
            user_id          TEXT NOT NULL,
            created_at       TEXT NOT NULL,
            meta_json        TEXT,
            UNIQUE(platform, platform_user_id)
        )"""
    )
    op.execute(
        """INSERT INTO im_users (id, platform, platform_user_id, user_id, created_at, meta_json)
           SELECT id, platform, platform_user_id, user_id, created_at, meta_json
           FROM im_users_current_079"""
    )
    op.execute("DROP TABLE im_users_current_079")
