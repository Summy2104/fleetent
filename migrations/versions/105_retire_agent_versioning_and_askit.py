"""Retire agent versioning and askit.

Revision ID: 105
Revises: 104
Create Date: 2026-06-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "105"
down_revision = "104"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_table("agents"):
        return

    if not _has_column("agents", "version"):
        op.add_column("agents", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    if not _has_column("agents", "model_overrides"):
        op.add_column(
            "agents",
            sa.Column("model_overrides", sa.Text(), nullable=False, server_default="{}"),
        )
    if not _has_column("agents", "memory_namespace"):
        op.add_column(
            "agents",
            sa.Column("memory_namespace", sa.Text(), nullable=False, server_default="default"),
        )
    if not _has_column("agents", "skills_dir"):
        op.add_column("agents", sa.Column("skills_dir", sa.Text(), nullable=True))

    if _has_table("agent_versions") and _has_column("agents", "active_version_id"):
        op.execute(
            sa.text(
                """
                UPDATE agents
                SET
                    version = COALESCE(
                        (SELECT av.version FROM agent_versions av WHERE av.id = agents.active_version_id),
                        version
                    ),
                    system_prompt = COALESCE(
                        (SELECT av.system_prompt FROM agent_versions av WHERE av.id = agents.active_version_id),
                        system_prompt
                    ),
                    allowed_tools = COALESCE(
                        (SELECT av.allowed_tools FROM agent_versions av WHERE av.id = agents.active_version_id),
                        allowed_tools
                    ),
                    model_overrides = COALESCE(
                        (SELECT av.model_overrides FROM agent_versions av WHERE av.id = agents.active_version_id),
                        model_overrides
                    ),
                    memory_namespace = COALESCE(
                        (SELECT av.memory_namespace FROM agent_versions av WHERE av.id = agents.active_version_id),
                        memory_namespace
                    ),
                    skills_dir = (
                        SELECT av.skills_dir FROM agent_versions av WHERE av.id = agents.active_version_id
                    )
                WHERE active_version_id IS NOT NULL
                """
            )
        )

    if _has_table("agent_versions"):
        op.drop_table("agent_versions")

    if _has_column("agents", "active_version_id"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.drop_column("active_version_id")

    if _has_table("agent_admin_state"):
        with op.batch_alter_table("agent_admin_state") as batch_op:
            if _has_column("agent_admin_state", "provenance"):
                batch_op.drop_column("provenance")
            if _has_column("agent_admin_state", "drift"):
                batch_op.drop_column("drift")


def downgrade() -> None:
    if not _has_table("agents"):
        return
    if not _has_column("agents", "active_version_id"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.add_column(sa.Column("active_version_id", sa.Integer(), nullable=True))

    if not _has_table("agent_versions"):
        op.create_table(
            "agent_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("system_prompt", sa.Text(), nullable=False),
            sa.Column("allowed_tools", sa.Text(), nullable=False),
            sa.Column("skills_dir", sa.Text(), nullable=True),
            sa.Column("mcp_server_ids", sa.Text(), nullable=True),
            sa.Column("model_overrides", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("memory_namespace", sa.Text(), nullable=False, server_default="default"),
            sa.Column("created_by_user_id", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("agent_id", "version"),
        )
        op.create_index("idx_agent_versions_agent", "agent_versions", ["agent_id"])
        op.execute(
            sa.text(
                """
                INSERT INTO agent_versions
                    (agent_id, version, system_prompt, allowed_tools, skills_dir,
                     mcp_server_ids, model_overrides, memory_namespace, created_by_user_id, created_at)
                SELECT
                    id,
                    COALESCE(version, 1),
                    system_prompt,
                    allowed_tools,
                    skills_dir,
                    NULL,
                    COALESCE(model_overrides, '{}'),
                    COALESCE(memory_namespace, 'default'),
                    NULL,
                    created_at
                FROM agents
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE agents
                SET active_version_id = (
                    SELECT av.id FROM agent_versions av
                    WHERE av.agent_id = agents.id AND av.version = COALESCE(agents.version, 1)
                )
                """
            )
        )

    if _has_table("agent_admin_state"):
        with op.batch_alter_table("agent_admin_state") as batch_op:
            if not _has_column("agent_admin_state", "provenance"):
                batch_op.add_column(
                    sa.Column("provenance", sa.Text(), nullable=False, server_default="adhoc")
                )
            if not _has_column("agent_admin_state", "drift"):
                batch_op.add_column(sa.Column("drift", sa.Integer(), nullable=False, server_default="0"))

    if _has_column("agents", "skills_dir"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.drop_column("skills_dir")
    if _has_column("agents", "memory_namespace"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.drop_column("memory_namespace")
    if _has_column("agents", "model_overrides"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.drop_column("model_overrides")
    if _has_column("agents", "version"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.drop_column("version")
