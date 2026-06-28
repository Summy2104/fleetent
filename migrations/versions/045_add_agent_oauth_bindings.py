"""add agent_oauth_bindings per-agent OAuth connector binding table

A binding is a join row: "agent X may use OAuth connector Y" (connectors defined in
the connector config catalog). Parallels agent_mcp_server_bindings (migration 041) for
MCP servers. Authoring metadata only; runtime consumption is a separate follow-up.

Revision ID: 045
Revises: 044
Create Date: 2026-06-04

Owner module: connector-management
"""

import sqlalchemy as sa
from alembic import op

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    op.create_table(
        "agent_oauth_bindings",
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("connector_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("agent_id", "connector_id"),
    )


def downgrade() -> None:
    if _has_table("agent_oauth_bindings"):
        op.drop_table("agent_oauth_bindings")
