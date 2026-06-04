"""add agent_mcp_server_bindings per-agent MCP binding table

A binding is a join row: "agent X may use the global MCP server named Y" (servers
defined in config/mcp.servers.yaml). Distinct from agent_mcp_servers (migration 040),
which holds full per-agent server *definitions* (transport/url/...). The two were
merged onto the same name during a branch integration; this migration owns the
binding side under its own table to avoid the schema collision.

Revision ID: 041
Revises: 040
Create Date: 2026-06-03

Owner module: agent-management
"""

import sqlalchemy as sa
from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_mcp_server_bindings",
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("server_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("agent_id", "server_id"),
    )


def downgrade() -> None:
    op.drop_table("agent_mcp_server_bindings")
