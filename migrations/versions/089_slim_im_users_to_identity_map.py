"""Slim im_users to an identity-only mapping.

Revision ID: 089
Revises: 088
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None

_SYSTEM_OWNER_ID = "__system__"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _column_names(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def _admin_owner_id(bind: sa.Connection) -> str:
    row = bind.execute(sa.text("SELECT id FROM users WHERE role = 'built_in_admin' LIMIT 1")).fetchone()
    return str(row[0]) if row is not None else _SYSTEM_OWNER_ID


def upgrade() -> None:
    if not _has_table("im_users"):
        return

    columns = _column_names("im_users")
    if "owner_id" not in columns and "allowed" not in columns:
        return

    bind = op.get_bind()
    op.execute("ALTER TABLE im_users RENAME TO im_users_legacy_089")
    op.execute(
        """
        CREATE TABLE im_users (
            id INTEGER PRIMARY KEY,
            platform TEXT NOT NULL,
            platform_user_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            meta_json TEXT,
            UNIQUE(platform, platform_user_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO im_users (id, platform, platform_user_id, user_id, created_at, meta_json)
            SELECT legacy.id,
                   legacy.platform,
                   legacy.platform_user_id,
                   legacy.user_id,
                   legacy.created_at,
                   legacy.meta_json
            FROM im_users_legacy_089 AS legacy
            JOIN (
                SELECT platform, platform_user_id, MIN(id) AS keep_id
                FROM im_users_legacy_089
                GROUP BY platform, platform_user_id
            ) AS dedup
              ON dedup.keep_id = legacy.id
            """
        )
    )
    op.execute("DROP TABLE im_users_legacy_089")


def downgrade() -> None:
    if not _has_table("im_users"):
        return

    columns = _column_names("im_users")
    if "owner_id" in columns and "allowed" in columns:
        return

    bind = op.get_bind()
    owner_id = _admin_owner_id(bind)
    op.execute("ALTER TABLE im_users RENAME TO im_users_current_089")
    op.execute(
        """
        CREATE TABLE im_users (
            id INTEGER PRIMARY KEY,
            owner_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            platform_user_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            allowed BOOLEAN NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            meta_json TEXT,
            UNIQUE(owner_id, platform, platform_user_id)
        )
        """
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO im_users
                (id, owner_id, platform, platform_user_id, user_id, allowed, created_at, meta_json)
            SELECT id,
                   :owner_id,
                   platform,
                   platform_user_id,
                   user_id,
                   1,
                   created_at,
                   meta_json
            FROM im_users_current_089
            """
        ),
        {"owner_id": owner_id},
    )
    op.execute("DROP TABLE im_users_current_089")
