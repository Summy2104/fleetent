"""Uniquify users.email per tenant after normalization.

Revision ID: 100
Revises: 099
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "100"
down_revision = "099"
branch_labels = None
depends_on = None

_INDEX_NAME = "uq_users_tenant_email_not_null"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _index_names(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if not _has_table("users"):
        return

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE users SET email = lower(trim(email)) WHERE email IS NOT NULL"))
    duplicates = bind.execute(
        sa.text(
            """
            SELECT tenant_id, email, COUNT(*) AS duplicate_count
            FROM users
            WHERE email IS NOT NULL
            GROUP BY tenant_id, email
            HAVING COUNT(*) > 1
            ORDER BY tenant_id, email
            """
        )
    ).fetchall()
    if duplicates:
        report = ", ".join(
            f"{row.tenant_id}:{row.email} (count={row.duplicate_count})" for row in duplicates
        )
        raise RuntimeError(f"duplicate normalized user emails found; aborting migration: {report}")

    if _INDEX_NAME in _index_names("users"):
        return

    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX uq_users_tenant_email_not_null
            ON users (tenant_id, email)
            WHERE email IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    if not _has_table("users"):
        return
    if _INDEX_NAME not in _index_names("users"):
        return
    op.drop_index(_INDEX_NAME, table_name="users")
