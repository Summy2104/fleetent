"""add enabled column to agent_mcp_servers

Lets a per-agent/global MCP server definition be deactivated without deleting it:
disabled rows keep their config but are skipped when resolving an agent's tools.
Existing rows default to enabled (1) for backward compatibility.

Revision ID: 043
Revises: 042
Create Date: 2026-06-04

Owner module: connector-management
"""

import sqlalchemy as sa
from alembic import op

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_mcp_servers",
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("agent_mcp_servers", "enabled")
