"""Unify agent_kbs and agent_skills agent_id columns to INTEGER foreign keys.

Revision ID: 082
Revises: 081
Create Date: 2026-06-13
"""

import sqlalchemy as sa
from alembic import op

revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _rebuild_agent_kbs_upgrade() -> None:
    if not _has_table("agent_kbs"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_kbs__new (
            tenant_id TEXT NOT NULL,
            kb_id TEXT NOT NULL,
            agent_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT,
            PRIMARY KEY (tenant_id, kb_id, agent_id),
            FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_kbs__new (tenant_id, kb_id, agent_id, created_at, created_by)
        SELECT tenant_id, kb_id, CAST(agent_id AS INTEGER), created_at, created_by
        FROM agent_kbs
        WHERE agent_id != '' AND agent_id NOT GLOB '*[^0-9]*'
        """
    )
    op.drop_index("idx_agent_kbs_agent", table_name="agent_kbs")
    op.drop_table("agent_kbs")
    op.rename_table("agent_kbs__new", "agent_kbs")
    op.create_index("idx_agent_kbs_agent", "agent_kbs", ["tenant_id", "agent_id"])


def _rebuild_agent_skills_upgrade() -> None:
    if not _has_table("agent_skills"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_skills__new (
            agent_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            PRIMARY KEY (agent_id, skill_name),
            FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
        )
        """
    )
    bind.exec_driver_sql(
        """
        WITH migrated AS (
            SELECT
                CAST(agent_id AS INTEGER) AS agent_id,
                skill_name,
                enabled,
                updated_at,
                updated_by,
                rowid AS source_rowid
            FROM agent_skills
            WHERE agent_id != '' AND agent_id NOT GLOB '*[^0-9]*'
            UNION ALL
            SELECT
                agents.id AS agent_id,
                agent_skills.skill_name,
                agent_skills.enabled,
                agent_skills.updated_at,
                agent_skills.updated_by,
                agent_skills.rowid AS source_rowid
            FROM agent_skills
            JOIN agents ON agent_skills.agent_id = agents.name
            WHERE agent_skills.agent_id = '' OR agent_skills.agent_id GLOB '*[^0-9]*'
        ),
        ranked AS (
            SELECT
                agent_id,
                skill_name,
                enabled,
                updated_at,
                updated_by,
                ROW_NUMBER() OVER (
                    PARTITION BY agent_id, skill_name
                    ORDER BY updated_at DESC, source_rowid DESC
                ) AS rn
            FROM migrated
        )
        INSERT INTO agent_skills__new (agent_id, skill_name, enabled, updated_at, updated_by)
        SELECT agent_id, skill_name, enabled, updated_at, updated_by
        FROM ranked
        WHERE rn = 1
        """
    )
    op.drop_index("idx_agent_skills_skill", table_name="agent_skills")
    op.drop_table("agent_skills")
    op.rename_table("agent_skills__new", "agent_skills")
    op.create_index("idx_agent_skills_skill", "agent_skills", ["skill_name"])


def _rebuild_agent_kbs_downgrade() -> None:
    if not _has_table("agent_kbs"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_kbs__old (
            tenant_id TEXT NOT NULL,
            kb_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT,
            PRIMARY KEY (tenant_id, kb_id, agent_id)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_kbs__old (tenant_id, kb_id, agent_id, created_at, created_by)
        SELECT tenant_id, kb_id, CAST(agent_id AS TEXT), created_at, created_by
        FROM agent_kbs
        """
    )
    op.drop_index("idx_agent_kbs_agent", table_name="agent_kbs")
    op.drop_table("agent_kbs")
    op.rename_table("agent_kbs__old", "agent_kbs")
    op.create_index("idx_agent_kbs_agent", "agent_kbs", ["tenant_id", "agent_id"])


def _rebuild_agent_skills_downgrade() -> None:
    if not _has_table("agent_skills"):
        return
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_skills__old (
            agent_id TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            PRIMARY KEY (agent_id, skill_name)
        )
        """
    )
    bind.exec_driver_sql(
        """
        INSERT INTO agent_skills__old (agent_id, skill_name, enabled, updated_at, updated_by)
        SELECT CAST(agent_id AS TEXT), skill_name, enabled, updated_at, updated_by
        FROM agent_skills
        """
    )
    op.drop_index("idx_agent_skills_skill", table_name="agent_skills")
    op.drop_table("agent_skills")
    op.rename_table("agent_skills__old", "agent_skills")
    op.create_index("idx_agent_skills_skill", "agent_skills", ["skill_name"])


def upgrade() -> None:
    _rebuild_agent_kbs_upgrade()
    _rebuild_agent_skills_upgrade()


def downgrade() -> None:
    _rebuild_agent_skills_downgrade()
    _rebuild_agent_kbs_downgrade()
