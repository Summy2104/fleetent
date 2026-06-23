"""Add schedule columns to kb_connectors.

Revision ID: 101
Revises: 100
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "101"
down_revision = "100"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    return column in cols


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("kb_connectors"):
        return
    if not _has_column("kb_connectors", "sync_interval_seconds"):
        op.add_column(
            "kb_connectors",
            sa.Column("sync_interval_seconds", sa.Integer(), nullable=True),
        )
    if not _has_column("kb_connectors", "last_scheduled_sync_at"):
        op.add_column(
            "kb_connectors",
            sa.Column("last_scheduled_sync_at", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if not _has_table("kb_connectors"):
        return
    if _has_column("kb_connectors", "last_scheduled_sync_at"):
        op.drop_column("kb_connectors", "last_scheduled_sync_at")
    if _has_column("kb_connectors", "sync_interval_seconds"):
        op.drop_column("kb_connectors", "sync_interval_seconds")
