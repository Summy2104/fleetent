"""mcp approval_rules: move from server definition to per-agent binding

Adds ``approval_rules`` to ``agent_mcp_servers`` (per agent<->server binding) and
drops it from ``mcp_servers`` (server definition). Approval policy is per-agent, so
each binding carries its own rules; the server definition no longer holds them.

Revision ID: 119
Revises: 118
Create Date: 2026-07-06

Owner module: connector-management / agent-management
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "119"
down_revision = "118"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table("agent_mcp_servers"):
        op.add_column(
            "agent_mcp_servers",
            sa.Column("approval_rules", sa.JSON(), nullable=False, server_default="[]"),
        )
    if _has_table("mcp_servers"):
        with op.batch_alter_table("mcp_servers") as batch_op:
            batch_op.drop_column("approval_rules")


def downgrade() -> None:
    if _has_table("mcp_servers"):
        op.add_column(
            "mcp_servers",
            sa.Column("approval_rules", sa.JSON(), nullable=False, server_default="[]"),
        )
    if _has_table("agent_mcp_servers"):
        with op.batch_alter_table("agent_mcp_servers") as batch_op:
            batch_op.drop_column("approval_rules")
