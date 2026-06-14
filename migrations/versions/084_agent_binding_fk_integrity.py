"""Add agent binding foreign keys and rename MCP registry/binding tables.

Revision ID: 084
Revises: 083
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _rename_mcp_tables_upgrade() -> None:
    if _has_table("agent_mcp_servers"):
        op.rename_table("agent_mcp_servers", "mcp_servers")
    if _has_table("agent_mcp_server_bindings"):
        op.rename_table("agent_mcp_server_bindings", "agent_mcp_servers")
    if _has_table("mcp_servers"):
        op.drop_index("idx_agent_mcp_servers_agent", table_name="mcp_servers")
        op.create_index("idx_mcp_servers_agent", "mcp_servers", ["agent_id", "server_id"])


def _rename_mcp_tables_downgrade() -> None:
    if _has_table("mcp_servers"):
        op.drop_index("idx_mcp_servers_agent", table_name="mcp_servers")
        op.create_index("idx_agent_mcp_servers_agent", "mcp_servers", ["agent_id", "server_id"])
    if _has_table("agent_mcp_servers"):
        op.rename_table("agent_mcp_servers", "agent_mcp_server_bindings")
    if _has_table("mcp_servers"):
        op.rename_table("mcp_servers", "agent_mcp_servers")


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


def _rebuild_user_agents_upgrade() -> None:
    if not _has_table("user_agents"):
        return
    _delete_orphans("user_agents")
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE user_agents__new (
            user_id TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, agent_id),
            FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO user_agents__new (user_id, agent_id)
        SELECT user_id, agent_id FROM user_agents
        """
    )
    op.drop_table("user_agents")
    op.rename_table("user_agents__new", "user_agents")


def _rebuild_user_agents_downgrade() -> None:
    if not _has_table("user_agents"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE user_agents__old (
            user_id TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, agent_id)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO user_agents__old (user_id, agent_id)
        SELECT user_id, agent_id FROM user_agents
        """
    )
    op.drop_table("user_agents")
    op.rename_table("user_agents__old", "user_agents")


def _rebuild_channel_agents_upgrade() -> None:
    if not _has_table("channel_agents"):
        return
    _delete_orphans("channel_agents")
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE channel_agents__new (
            id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            bound_version_id INTEGER,
            PRIMARY KEY (id),
            UNIQUE (platform, channel_id),
            FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO channel_agents__new
            (id, platform, channel_id, agent_id, created_at, bound_version_id)
        SELECT id, platform, channel_id, agent_id, created_at, bound_version_id
        FROM channel_agents
        """
    )
    op.drop_table("channel_agents")
    op.rename_table("channel_agents__new", "channel_agents")


def _rebuild_channel_agents_downgrade() -> None:
    if not _has_table("channel_agents"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE channel_agents__old (
            id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            bound_version_id INTEGER,
            PRIMARY KEY (id),
            UNIQUE (platform, channel_id)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO channel_agents__old
            (id, platform, channel_id, agent_id, created_at, bound_version_id)
        SELECT id, platform, channel_id, agent_id, created_at, bound_version_id
        FROM channel_agents
        """
    )
    op.drop_table("channel_agents")
    op.rename_table("channel_agents__old", "channel_agents")


def _rebuild_agent_versions_upgrade() -> None:
    if not _has_table("agent_versions"):
        return
    _delete_orphans("agent_versions")
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_versions__new (
            id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            system_prompt TEXT NOT NULL,
            allowed_tools TEXT NOT NULL,
            skills_dir TEXT,
            mcp_server_ids TEXT,
            model_overrides TEXT NOT NULL DEFAULT '{}',
            memory_namespace TEXT NOT NULL DEFAULT 'default',
            created_by_user_id TEXT,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (agent_id, version),
            FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_versions__new
            (id, agent_id, version, system_prompt, allowed_tools, skills_dir,
             mcp_server_ids, model_overrides, memory_namespace, created_by_user_id, created_at)
        SELECT
            id, agent_id, version, system_prompt, allowed_tools, skills_dir,
            mcp_server_ids, model_overrides, memory_namespace, created_by_user_id, created_at
        FROM agent_versions
        """
    )
    op.drop_index("idx_agent_versions_agent", table_name="agent_versions")
    op.drop_table("agent_versions")
    op.rename_table("agent_versions__new", "agent_versions")
    op.create_index("idx_agent_versions_agent", "agent_versions", ["agent_id"])


def _rebuild_agent_versions_downgrade() -> None:
    if not _has_table("agent_versions"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_versions__old (
            id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            system_prompt TEXT NOT NULL,
            allowed_tools TEXT NOT NULL,
            skills_dir TEXT,
            mcp_server_ids TEXT,
            model_overrides TEXT NOT NULL DEFAULT '{}',
            memory_namespace TEXT NOT NULL DEFAULT 'default',
            created_by_user_id TEXT,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (agent_id, version)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_versions__old
            (id, agent_id, version, system_prompt, allowed_tools, skills_dir,
             mcp_server_ids, model_overrides, memory_namespace, created_by_user_id, created_at)
        SELECT
            id, agent_id, version, system_prompt, allowed_tools, skills_dir,
            mcp_server_ids, model_overrides, memory_namespace, created_by_user_id, created_at
        FROM agent_versions
        """
    )
    op.drop_index("idx_agent_versions_agent", table_name="agent_versions")
    op.drop_table("agent_versions")
    op.rename_table("agent_versions__old", "agent_versions")
    op.create_index("idx_agent_versions_agent", "agent_versions", ["agent_id"])


def _rebuild_mcp_servers_upgrade() -> None:
    if not _has_table("mcp_servers"):
        return
    _delete_orphans("mcp_servers")
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE mcp_servers__new (
            id INTEGER NOT NULL,
            agent_id INTEGER,
            server_id TEXT NOT NULL,
            transport TEXT NOT NULL DEFAULT 'http',
            url TEXT NOT NULL DEFAULT '',
            auth_type TEXT NOT NULL DEFAULT 'none',
            api_key_env TEXT NOT NULL DEFAULT '',
            command TEXT NOT NULL DEFAULT '',
            args TEXT,
            env TEXT,
            created_at TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            headers TEXT,
            PRIMARY KEY (id),
            UNIQUE (agent_id, server_id),
            FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO mcp_servers__new
            (id, agent_id, server_id, transport, url, auth_type, api_key_env,
             command, args, env, created_at, enabled, headers)
        SELECT
            id, agent_id, server_id, transport, url, auth_type, api_key_env,
            command, args, env, created_at, enabled, headers
        FROM mcp_servers
        """
    )
    op.drop_index("idx_mcp_servers_agent", table_name="mcp_servers")
    op.drop_table("mcp_servers")
    op.rename_table("mcp_servers__new", "mcp_servers")
    op.create_index("idx_mcp_servers_agent", "mcp_servers", ["agent_id", "server_id"])


def _rebuild_mcp_servers_downgrade() -> None:
    if not _has_table("mcp_servers"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE mcp_servers__old (
            id INTEGER NOT NULL,
            agent_id INTEGER,
            server_id TEXT NOT NULL,
            transport TEXT NOT NULL DEFAULT 'http',
            url TEXT NOT NULL DEFAULT '',
            auth_type TEXT NOT NULL DEFAULT 'none',
            api_key_env TEXT NOT NULL DEFAULT '',
            command TEXT NOT NULL DEFAULT '',
            args TEXT,
            env TEXT,
            created_at TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            headers TEXT,
            PRIMARY KEY (id),
            UNIQUE (agent_id, server_id)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO mcp_servers__old
            (id, agent_id, server_id, transport, url, auth_type, api_key_env,
             command, args, env, created_at, enabled, headers)
        SELECT
            id, agent_id, server_id, transport, url, auth_type, api_key_env,
            command, args, env, created_at, enabled, headers
        FROM mcp_servers
        """
    )
    op.drop_index("idx_mcp_servers_agent", table_name="mcp_servers")
    op.drop_table("mcp_servers")
    op.rename_table("mcp_servers__old", "mcp_servers")
    op.create_index("idx_mcp_servers_agent", "mcp_servers", ["agent_id", "server_id"])


def _rebuild_agent_secrets_upgrade() -> None:
    if not _has_table("agent_secrets"):
        return
    _delete_orphans("agent_secrets")
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_secrets__new (
            agent_id INTEGER,
            env_name TEXT NOT NULL,
            ciphertext TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_secrets__new
            (agent_id, env_name, ciphertext, updated_at, updated_by)
        SELECT agent_id, env_name, ciphertext, updated_at, updated_by
        FROM agent_secrets
        """
    )
    op.drop_index("ux_agent_secrets_scope", table_name="agent_secrets")
    op.drop_table("agent_secrets")
    op.rename_table("agent_secrets__new", "agent_secrets")
    op.create_index(
        "ux_agent_secrets_scope",
        "agent_secrets",
        [sa.text("COALESCE(agent_id, -1)"), "env_name"],
        unique=True,
    )


def _rebuild_agent_secrets_downgrade() -> None:
    if not _has_table("agent_secrets"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_secrets__old (
            agent_id INTEGER,
            env_name TEXT NOT NULL,
            ciphertext TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_secrets__old
            (agent_id, env_name, ciphertext, updated_at, updated_by)
        SELECT agent_id, env_name, ciphertext, updated_at, updated_by
        FROM agent_secrets
        """
    )
    op.drop_index("ux_agent_secrets_scope", table_name="agent_secrets")
    op.drop_table("agent_secrets")
    op.rename_table("agent_secrets__old", "agent_secrets")
    op.create_index(
        "ux_agent_secrets_scope",
        "agent_secrets",
        [sa.text("COALESCE(agent_id, -1)"), "env_name"],
        unique=True,
    )


def upgrade() -> None:
    _rename_mcp_tables_upgrade()
    _rebuild_user_agents_upgrade()
    _rebuild_channel_agents_upgrade()
    _rebuild_agent_versions_upgrade()
    _rebuild_mcp_servers_upgrade()
    _rebuild_agent_secrets_upgrade()


def downgrade() -> None:
    _rebuild_agent_secrets_downgrade()
    _rebuild_mcp_servers_downgrade()
    _rebuild_agent_versions_downgrade()
    _rebuild_channel_agents_downgrade()
    _rebuild_user_agents_downgrade()
    _rename_mcp_tables_downgrade()
