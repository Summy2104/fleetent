"""descope im channel allowlist

Revision ID: 090
Revises: 089
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "090"
down_revision = "089"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _column_names(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if _has_table("im_channel_allowlist"):
        op.drop_table("im_channel_allowlist")

    if _has_table("im_connectors") and "allowlist_enforced" in _column_names("im_connectors"):
        with op.batch_alter_table("im_connectors") as batch_op:
            batch_op.drop_column("allowlist_enforced")


def downgrade() -> None:
    if _has_table("im_connectors") and "allowlist_enforced" not in _column_names("im_connectors"):
        with op.batch_alter_table("im_connectors") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "allowlist_enforced",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )

    if not _has_table("im_channel_allowlist"):
        op.create_table(
            "im_channel_allowlist",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("owner_id", sa.Text(), nullable=False),
            sa.Column("platform", sa.Text(), nullable=False),
            sa.Column("scope_type", sa.Text(), nullable=False),
            sa.Column("scope_id", sa.Text(), nullable=False),
            sa.Column("allowed", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("owner_id", "platform", "scope_type", "scope_id"),
        )
