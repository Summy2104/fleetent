"""descope im owner-level connectors

Revision ID: 091
Revises: 090
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "091"
down_revision = "090"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table("im_connectors"):
        op.drop_table("im_connectors")


def downgrade() -> None:
    if _has_table("im_connectors"):
        return

    op.create_table(
        "im_connectors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="stopped"),
        sa.Column("last_heartbeat_at", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("owner_id", "platform"),
    )
