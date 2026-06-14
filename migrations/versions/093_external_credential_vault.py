"""Introduce external credential vault tables and names.

Replaces the dormant tool OAuth schema with the first per-user external credential
vault slice:

- ``connectors`` -> ``external_services`` and remove the dormant ``agent_id`` overlay
- ``agent_oauth_bindings`` -> ``agent_service_grants`` with ``run_as``
- add ``external_credentials`` for encrypted per-(user, service) credentials

SQLite cannot reshape these tables in place, so the migration follows the
"create new table -> copy data -> drop old table" pattern used elsewhere.

Revision ID: 093
Revises: 092
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "093"
down_revision = "092"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _rebuild_external_services(*, downgrade: bool) -> None:
    bind = op.get_bind()
    if downgrade:
        if not _has_table("external_services"):
            return
        bind.exec_driver_sql(
            """
            CREATE TABLE connectors (
                agent_id INTEGER,
                id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                protocol TEXT NOT NULL DEFAULT 'oauth2',
                oauth_config TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        bind.exec_driver_sql(
            """
            INSERT INTO connectors
                (agent_id, id, display_name, protocol, oauth_config, enabled, created_at, updated_at)
            SELECT
                NULL,
                service_id,
                display_name,
                protocol,
                oauth_config,
                enabled,
                created_at,
                updated_at
            FROM external_services
            """
        )
        op.drop_table("external_services")
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
        return

    if not _has_table("connectors"):
        return
    bind.exec_driver_sql(
        """
        CREATE TABLE external_services (
            service_id TEXT NOT NULL PRIMARY KEY,
            display_name TEXT NOT NULL,
            protocol TEXT NOT NULL DEFAULT 'oauth2',
            oauth_config TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO external_services
            (service_id, display_name, protocol, oauth_config, enabled, created_at, updated_at)
        SELECT
            id,
            display_name,
            protocol,
            oauth_config,
            enabled,
            created_at,
            updated_at
        FROM connectors
        WHERE agent_id IS NULL
        """
    )
    op.drop_table("connectors")


def _rebuild_agent_service_grants(*, downgrade: bool) -> None:
    bind = op.get_bind()
    if downgrade:
        if not _has_table("agent_service_grants"):
            return
        bind.exec_driver_sql(
            """
            CREATE TABLE agent_oauth_bindings (
                agent_id INTEGER NOT NULL,
                connector_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT,
                PRIMARY KEY (agent_id, connector_id),
                FOREIGN KEY(agent_id) REFERENCES agents(id)
            )
            """
        )
        bind.exec_driver_sql(
            """
            INSERT INTO agent_oauth_bindings (agent_id, connector_id, created_at, created_by)
            SELECT agent_id, service_id, created_at, created_by
            FROM agent_service_grants
            """
        )
        op.drop_table("agent_service_grants")
        return

    if not _has_table("agent_oauth_bindings"):
        return
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_service_grants (
            agent_id INTEGER NOT NULL,
            service_id TEXT NOT NULL,
            run_as TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL,
            created_by TEXT,
            PRIMARY KEY (agent_id, service_id),
            FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_service_grants (agent_id, service_id, run_as, created_at, created_by)
        SELECT agent_id, connector_id, 'user', created_at, created_by
        FROM agent_oauth_bindings
        """
    )
    op.drop_table("agent_oauth_bindings")


def upgrade() -> None:
    _rebuild_external_services(downgrade=False)
    _rebuild_agent_service_grants(downgrade=False)
    op.create_table(
        "external_credentials",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("service_id", sa.Text(), nullable=False),
        sa.Column("payload_ciphertext", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("user_id", "service_id"),
    )


def downgrade() -> None:
    op.drop_table("external_credentials")
    _rebuild_agent_service_grants(downgrade=True)
    _rebuild_external_services(downgrade=True)
