"""add backflow_proposals table for agent skill backflow governance

Revision ID: 094
Revises: 093
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "094"
down_revision = "093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backflow_proposals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("skill_name", sa.Text(), nullable=False),
        sa.Column("base_version", sa.Text(), nullable=True),
        sa.Column("proposed_content", sa.Text(), nullable=False),
        sa.Column("conflict", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overridden_head", sa.Text(), nullable=True),
        sa.Column("forked_as", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_backflow_proposals_skill_status",
        "backflow_proposals",
        ["skill_name", "status"],
    )
    op.create_index(
        "idx_backflow_proposals_agent_skill",
        "backflow_proposals",
        ["agent_id", "skill_name"],
    )


def downgrade() -> None:
    op.drop_index("idx_backflow_proposals_agent_skill", table_name="backflow_proposals")
    op.drop_index("idx_backflow_proposals_skill_status", table_name="backflow_proposals")
    op.drop_table("backflow_proposals")
