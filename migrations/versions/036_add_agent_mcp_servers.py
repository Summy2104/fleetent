"""add agent_mcp_servers per-agent MCP binding table

Revision ID: 036
Revises: 035
Create Date: 2026-06-03

Owner module: agent-management
"""

import sqlalchemy as sa
from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_mcp_servers",
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("server_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("agent_id", "server_id"),
    )


def downgrade() -> None:
    op.drop_table("agent_mcp_servers")
