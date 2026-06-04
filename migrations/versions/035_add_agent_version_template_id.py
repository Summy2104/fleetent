"""add template_id column to agent_versions

Revision ID: 035
Revises: 034
Create Date: 2026-06-03

Owner module: agent-management
"""

import sqlalchemy as sa
from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_versions",
        sa.Column("template_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("agent_versions") as batch_op:
        batch_op.drop_column("template_id")
