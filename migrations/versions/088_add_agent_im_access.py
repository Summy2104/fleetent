"""Add agent IM access scaffolding.

Revision ID: 088
Revises: 087
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _column_names(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if _has_table("agents") and not _has_table("agent_im_groups"):
        op.create_table(
            "agent_im_groups",
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("platform", sa.Text(), nullable=False),
            sa.Column("group_id", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("created_by", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("agent_id", "platform", "group_id"),
        )

    if not _has_table("agents"):
        return
    agent_columns = _column_names("agents")
    if "supports_dm" not in agent_columns:
        op.add_column(
            "agents",
            sa.Column(
                "supports_dm",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if "supports_groups" not in agent_columns:
        op.add_column(
            "agents",
            sa.Column(
                "supports_groups",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    if _has_table("agents"):
        agent_columns = _column_names("agents")
        with op.batch_alter_table("agents") as batch_op:
            if "supports_groups" in agent_columns:
                batch_op.drop_column("supports_groups")
            if "supports_dm" in agent_columns:
                batch_op.drop_column("supports_dm")

    if _has_table("agent_im_groups"):
        op.drop_table("agent_im_groups")
