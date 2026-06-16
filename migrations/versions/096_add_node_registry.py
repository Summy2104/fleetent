"""add node registry management tables

Revision ID: 096
Revises: 095
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "096"
down_revision = "095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("key_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("labels", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("registered_at", sa.Text(), nullable=False),
        sa.Column("last_seen_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "agent_placements",
        sa.Column(
            "agent_id",
            sa.Integer(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "node_id",
            sa.Text(),
            sa.ForeignKey("nodes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("pinned_at", sa.Text(), nullable=False),
        sa.Column("pinned_by", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_placements")
    op.drop_table("nodes")
