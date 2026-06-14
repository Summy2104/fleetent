"""redesign skill schema drift protection

Revision ID: 092
Revises: 091
Create Date: 2026-06-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "092"
down_revision = "091"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _create_skills_table() -> None:
    op.create_table(
        "skills",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("global_enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("audit_verdict", sa.Text(), nullable=True),
        sa.Column("audit_rules", sa.Text(), nullable=True),
        sa.Column("forced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.Text(), nullable=False, server_default="adhoc"),
        sa.Column("immutable_fields", sa.Text(), nullable=True),
        sa.Column("current_version", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )


def _backfill_skills() -> None:
    bind = op.get_bind()
    has_state = _has_table("skill_admin_state")
    has_provenance = _has_table("skill_provenance")
    has_agent_skills = _has_table("agent_skills")
    if has_state:
        provenance_join = (
            "LEFT JOIN skill_provenance AS p ON p.skill_name = s.skill_name"
            if has_provenance
            else ""
        )
        source_expr = "COALESCE(p.source, 'adhoc')" if has_provenance else "'adhoc'"
        immutable_expr = "p.immutable_fields" if has_provenance else "NULL"
        updated_expr = (
            "COALESCE(s.updated_at, p.updated_at, CURRENT_TIMESTAMP)"
            if has_provenance
            else "COALESCE(s.updated_at, CURRENT_TIMESTAMP)"
        )
        bind.exec_driver_sql(
            f"""
            INSERT INTO skills (
                name, status, global_enabled, audit_verdict, audit_rules, forced,
                source, immutable_fields, current_version, archived_at, created_at, updated_at
            )
            SELECT
                s.skill_name,
                s.status,
                s.global_enabled,
                s.audit_verdict,
                s.audit_rules,
                s.forced,
                {source_expr},
                {immutable_expr},
                NULL,
                s.archived_at,
                {updated_expr},
                {updated_expr}
            FROM skill_admin_state AS s
            {provenance_join}
            """
        )
    if has_provenance:
        missing_state_predicate = (
            "NOT EXISTS (SELECT 1 FROM skill_admin_state AS s WHERE s.skill_name = p.skill_name)"
            if has_state
            else "1 = 1"
        )
        bind.exec_driver_sql(
            f"""
            INSERT INTO skills (
                name, status, global_enabled, audit_verdict, audit_rules, forced,
                source, immutable_fields, current_version, archived_at, created_at, updated_at
            )
            SELECT
                p.skill_name,
                'active',
                1,
                NULL,
                NULL,
                0,
                p.source,
                p.immutable_fields,
                NULL,
                NULL,
                COALESCE(p.updated_at, CURRENT_TIMESTAMP),
                COALESCE(p.updated_at, CURRENT_TIMESTAMP)
            FROM skill_provenance AS p
            WHERE {missing_state_predicate}
            """
        )
    if has_agent_skills:
        bind.exec_driver_sql(
            """
            INSERT INTO skills (
                name, status, global_enabled, audit_verdict, audit_rules, forced,
                source, immutable_fields, current_version, archived_at, created_at, updated_at
            )
            SELECT
                a.skill_name,
                'active',
                1,
                NULL,
                NULL,
                0,
                'adhoc',
                NULL,
                NULL,
                NULL,
                COALESCE(MAX(a.updated_at), CURRENT_TIMESTAMP),
                COALESCE(MAX(a.updated_at), CURRENT_TIMESTAMP)
            FROM agent_skills AS a
            WHERE NOT EXISTS (SELECT 1 FROM skills AS s WHERE s.name = a.skill_name)
            GROUP BY a.skill_name
            """
        )


def _rebuild_agent_skills(*, include_drift_columns: bool) -> None:
    if not _has_table("agent_skills"):
        return

    bind = op.get_bind()
    if include_drift_columns:
        bind.exec_driver_sql(
            """
            CREATE TABLE agent_skills__new (
                agent_id INTEGER NOT NULL,
                skill_name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                updated_by TEXT,
                base_version TEXT,
                drift INTEGER NOT NULL DEFAULT 0,
                drift_at TEXT,
                PRIMARY KEY (agent_id, skill_name),
                FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE,
                FOREIGN KEY(skill_name) REFERENCES skills(name)
            )
            """
        )
        bind.exec_driver_sql(
            """
            INSERT INTO agent_skills__new (
                agent_id, skill_name, enabled, updated_at, updated_by, base_version, drift, drift_at
            )
            SELECT agent_id, skill_name, enabled, updated_at, updated_by, NULL, 0, NULL
            FROM agent_skills
            """
        )
    else:
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
            INSERT INTO agent_skills__new (agent_id, skill_name, enabled, updated_at, updated_by)
            SELECT agent_id, skill_name, enabled, updated_at, updated_by
            FROM agent_skills
            """
        )

    op.drop_table("agent_skills")
    op.rename_table("agent_skills__new", "agent_skills")
    op.create_index("idx_agent_skills_skill", "agent_skills", ["skill_name"])


def upgrade() -> None:
    _create_skills_table()
    _backfill_skills()
    _rebuild_agent_skills(include_drift_columns=True)
    if _has_table("skill_provenance"):
        op.drop_table("skill_provenance")
    if _has_table("skill_admin_state"):
        op.drop_table("skill_admin_state")


def downgrade() -> None:
    op.create_table(
        "skill_admin_state",
        sa.Column("skill_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("global_enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("audit_verdict", sa.Text(), nullable=True),
        sa.Column("audit_rules", sa.Text(), nullable=True),
        sa.Column("forced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived_at", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("skill_name"),
    )
    op.create_table(
        "skill_provenance",
        sa.Column("skill_name", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="adhoc"),
        sa.Column("drift", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("immutable_fields", sa.Text(), nullable=True),
        sa.Column("last_deploy_at", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("skill_name"),
    )
    op.get_bind().exec_driver_sql(
        """
        INSERT INTO skill_admin_state (
            skill_name, status, global_enabled, audit_verdict,
            audit_rules, forced, archived_at, updated_at
        )
        SELECT
            name, status, global_enabled, audit_verdict,
            audit_rules, forced, archived_at, updated_at
        FROM skills
        """
    )
    op.get_bind().exec_driver_sql(
        """
        INSERT INTO skill_provenance (
            skill_name, source, drift, immutable_fields, last_deploy_at, updated_at
        )
        SELECT name, source, 0, immutable_fields, NULL, updated_at
        FROM skills
        """
    )
    _rebuild_agent_skills(include_drift_columns=False)
    op.drop_table("skills")
