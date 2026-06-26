"""Add forward_host column to nodes.

Revision ID: 102
Revises: 101
Create Date: 2026-06-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "102"
down_revision = "101"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    return column in cols


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("nodes"):
        return
    if not _has_column("nodes", "forward_host"):
        op.add_column(
            "nodes",
            sa.Column("forward_host", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if not _has_table("nodes"):
        return
    if _has_column("nodes", "forward_host"):
        op.drop_column("nodes", "forward_host")
