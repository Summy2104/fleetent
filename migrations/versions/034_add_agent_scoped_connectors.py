"""Scope OAuth connectors and MCP servers by owning agent.

Recreates ``connectors`` with a nullable ``agent_id`` (null = global default) and
drops the old ``id``-only primary key so the same connector id can exist once per
agent plus once globally. Uniqueness is enforced by two partial indexes:
agent-scoped ``(agent_id, id)`` and global ``(id)`` where ``agent_id IS NULL``.
Also introduces an ``agent_mcp_servers`` table holding per-agent MCP server
definitions. Agent-owned rows override the global-default layer
(``config/mcp.servers.yaml`` for MCP, ``agent_id IS NULL`` rows for connectors).

Revision ID: 034
Revises: 033
Create Date: 2026-06-03

Owner module: connector-management
"""

import sqlalchemy as sa
from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite cannot drop a PRIMARY KEY in place; recreate the table to move from
    # PK(id) to a rowid table whose uniqueness is scoped by agent_id.
    op.rename_table("connectors", "connectors_old")
    op.create_table(
        "connectors",
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("protocol", sa.Text(), nullable=False, server_default="oauth2"),
        sa.Column("oauth_config", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.execute(
        """
        INSERT INTO connectors
            (agent_id, id, display_name, protocol, oauth_config, enabled, created_at, updated_at)
        SELECT NULL, id, display_name, protocol, oauth_config, enabled, created_at, updated_at
        FROM connectors_old
        """
    )
    op.drop_table("connectors_old")
    op.create_index(
        "ux_connectors_agent_scope",
        "connectors",
        ["agent_id", "id"],
        unique=True,
        sqlite_where=sa.text("agent_id IS NOT NULL"),
    )
    op.create_index(
        "ux_connectors_global_scope",
        "connectors",
        ["id"],
        unique=True,
        sqlite_where=sa.text("agent_id IS NULL"),
    )

    op.create_table(
        "agent_mcp_servers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("server_id", sa.Text(), nullable=False),
        sa.Column("transport", sa.Text(), nullable=False, server_default="http"),
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("auth_type", sa.Text(), nullable=False, server_default="none"),
        sa.Column("api_key_env", sa.Text(), nullable=False, server_default=""),
        sa.Column("command", sa.Text(), nullable=False, server_default=""),
        sa.Column("args", sa.Text(), nullable=True),
        sa.Column("env", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("agent_id", "server_id"),
    )
    op.create_index(
        "idx_agent_mcp_servers_agent", "agent_mcp_servers", ["agent_id", "server_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_agent_mcp_servers_agent", table_name="agent_mcp_servers")
    op.drop_table("agent_mcp_servers")

    op.drop_index("ux_connectors_agent_scope", table_name="connectors")
    op.drop_index("ux_connectors_global_scope", table_name="connectors")
    op.rename_table("connectors", "connectors_new")
    op.create_table(
        "connectors",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("protocol", sa.Text(), nullable=False, server_default="oauth2"),
        sa.Column("oauth_config", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO connectors
            (id, display_name, protocol, oauth_config, enabled, created_at, updated_at)
        SELECT id, display_name, protocol, oauth_config, enabled, created_at, updated_at
        FROM connectors_new
        WHERE agent_id IS NULL
        """
    )
    op.drop_table("connectors_new")
