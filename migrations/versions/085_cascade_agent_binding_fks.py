"""Upgrade agent MCP/OAuth binding-table FKs to ON DELETE CASCADE.

Migration 084 added FK→agents.id ON DELETE CASCADE to user_agents / channel_agents /
agent_versions / mcp_servers / agent_secrets, but left the two binding tables
``agent_mcp_servers`` (agent↔MCP server binding, originally agent_mcp_server_bindings)
and ``agent_oauth_bindings`` with their original plain ``FK(agents.id)`` (NO ACTION).
Deleting an agent therefore tripped a FK constraint unless the store cleared those
rows manually. This migration rebuilds both binding tables with ON DELETE CASCADE so
that deleting the ``agents`` row cascades to every agent-referencing table uniformly
(identity-model 阶段 4 的"agent 删除即级联清理全部绑定"对这两表也成立)，让 delete_agent
退化为单条 DELETE。

Revision ID: 085
Revises: 084
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _delete_orphans(table: str) -> None:
    op.execute(
        sa.text(
            f"""
            DELETE FROM {table}
            WHERE agent_id IS NOT NULL
              AND agent_id NOT IN (SELECT id FROM agents)
            """
        )
    )


def _rebuild_agent_mcp_servers(*, cascade: bool) -> None:
    if not _has_table("agent_mcp_servers"):
        return
    _delete_orphans("agent_mcp_servers")
    fk = "FOREIGN KEY(agent_id) REFERENCES agents(id)" + (" ON DELETE CASCADE" if cascade else "")
    bind = op.get_bind()
    bind.exec_driver_sql(
        f"""
        CREATE TABLE agent_mcp_servers__new (
            agent_id INTEGER NOT NULL,
            server_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT,
            PRIMARY KEY (agent_id, server_id),
            {fk}
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_mcp_servers__new (agent_id, server_id, created_at, created_by)
        SELECT agent_id, server_id, created_at, created_by FROM agent_mcp_servers
        """
    )
    op.drop_table("agent_mcp_servers")
    op.rename_table("agent_mcp_servers__new", "agent_mcp_servers")


def _rebuild_agent_oauth_bindings(*, cascade: bool) -> None:
    if not _has_table("agent_oauth_bindings"):
        return
    _delete_orphans("agent_oauth_bindings")
    fk = "FOREIGN KEY(agent_id) REFERENCES agents(id)" + (" ON DELETE CASCADE" if cascade else "")
    bind = op.get_bind()
    bind.exec_driver_sql(
        f"""
        CREATE TABLE agent_oauth_bindings__new (
            agent_id INTEGER NOT NULL,
            connector_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT,
            PRIMARY KEY (agent_id, connector_id),
            {fk}
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_oauth_bindings__new (agent_id, connector_id, created_at, created_by)
        SELECT agent_id, connector_id, created_at, created_by FROM agent_oauth_bindings
        """
    )
    op.drop_table("agent_oauth_bindings")
    op.rename_table("agent_oauth_bindings__new", "agent_oauth_bindings")


def upgrade() -> None:
    _rebuild_agent_mcp_servers(cascade=True)
    _rebuild_agent_oauth_bindings(cascade=True)


def downgrade() -> None:
    _rebuild_agent_oauth_bindings(cascade=False)
    _rebuild_agent_mcp_servers(cascade=False)
