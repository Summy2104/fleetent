"""add encrypted per-agent secret values

Revision ID: 053
Revises: 052
Create Date: 2026-06-06

Owner module: platform-agent-lifecycle
"""

import sqlalchemy as sa
from alembic import op

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_secrets",
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("env_name", sa.Text(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id", "env_name"),
    )


def downgrade() -> None:
    op.drop_table("agent_secrets")
