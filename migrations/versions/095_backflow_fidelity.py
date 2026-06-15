"""backflow fidelity fixes

Revision ID: 095
Revises: 094
Create Date: 2026-06-15
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "095"
down_revision = "094"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _upgrade_backflow_proposals() -> None:
    if not _has_table("backflow_proposals"):
        return

    bind = op.get_bind()
    rows = list(
        bind.exec_driver_sql(
            """
            SELECT
                id, status, agent_id, skill_name, base_version, proposed_content,
                conflict, overridden_head, forked_as, created_at, updated_at
            FROM backflow_proposals
            ORDER BY id
            """
        )
    )

    bind.exec_driver_sql(
        """
        CREATE TABLE backflow_proposals__new (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'pending',
            agent_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            base_version TEXT,
            base_commit TEXT,
            proposed_bundle TEXT NOT NULL,
            conflict INTEGER NOT NULL DEFAULT 0,
            overridden_head TEXT,
            forked_as TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    for row in rows:
        bind.exec_driver_sql(
            """
            INSERT INTO backflow_proposals__new (
                id, status, agent_id, skill_name, base_version, base_commit, proposed_bundle,
                conflict, overridden_head, forked_as, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                None,
                json.dumps({"SKILL.md": row[5]}),
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
            ),
        )

    op.drop_index("idx_backflow_proposals_agent_skill", table_name="backflow_proposals")
    op.drop_index("idx_backflow_proposals_skill_status", table_name="backflow_proposals")
    op.drop_table("backflow_proposals")
    op.rename_table("backflow_proposals__new", "backflow_proposals")
    op.create_index(
        "idx_backflow_proposals_skill_status",
        "backflow_proposals",
        ["skill_name", "status"],
    )
    op.create_index(
        "idx_backflow_proposals_agent_skill",
        "backflow_proposals",
        ["agent_id", "skill_name"],
    )


def _downgrade_backflow_proposals() -> None:
    if not _has_table("backflow_proposals"):
        return

    bind = op.get_bind()
    rows = list(
        bind.exec_driver_sql(
            """
            SELECT
                id, status, agent_id, skill_name, base_version, base_commit, proposed_bundle,
                conflict, overridden_head, forked_as, created_at, updated_at
            FROM backflow_proposals
            ORDER BY id
            """
        )
    )

    bind.exec_driver_sql(
        """
        CREATE TABLE backflow_proposals__old (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'pending',
            agent_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            base_version TEXT,
            proposed_content TEXT NOT NULL,
            conflict INTEGER NOT NULL DEFAULT 0,
            overridden_head TEXT,
            forked_as TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    for row in rows:
        bundle = json.loads(row[6]) if row[6] else {}
        proposed_content = bundle.get("SKILL.md", "")
        bind.exec_driver_sql(
            """
            INSERT INTO backflow_proposals__old (
                id, status, agent_id, skill_name, base_version, proposed_content,
                conflict, overridden_head, forked_as, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row[0],
                row[1],
                row[2],
                row[3],
                row[4],
                proposed_content,
                row[7],
                row[8],
                row[9],
                row[10],
                row[11],
            ),
        )

    op.drop_index("idx_backflow_proposals_agent_skill", table_name="backflow_proposals")
    op.drop_index("idx_backflow_proposals_skill_status", table_name="backflow_proposals")
    op.drop_table("backflow_proposals")
    op.rename_table("backflow_proposals__old", "backflow_proposals")
    op.create_index(
        "idx_backflow_proposals_skill_status",
        "backflow_proposals",
        ["skill_name", "status"],
    )
    op.create_index(
        "idx_backflow_proposals_agent_skill",
        "backflow_proposals",
        ["agent_id", "skill_name"],
    )


def _rebuild_agent_skills_without_base_commit() -> None:
    if not _has_table("agent_skills"):
        return

    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        CREATE TABLE agent_skills__old (
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
        INSERT INTO agent_skills__old (
            agent_id, skill_name, enabled, updated_at, updated_by, base_version, drift, drift_at
        )
        SELECT
            agent_id, skill_name, enabled, updated_at, updated_by, base_version, drift, drift_at
        FROM agent_skills
        """
    )
    op.drop_index("idx_agent_skills_skill", table_name="agent_skills")
    op.drop_table("agent_skills")
    op.rename_table("agent_skills__old", "agent_skills")
    op.create_index("idx_agent_skills_skill", "agent_skills", ["skill_name"])


def upgrade() -> None:
    if _has_table("agent_skills"):
        op.add_column("agent_skills", sa.Column("base_commit", sa.Text(), nullable=True))
    _upgrade_backflow_proposals()


def downgrade() -> None:
    _downgrade_backflow_proposals()
    _rebuild_agent_skills_without_base_commit()
