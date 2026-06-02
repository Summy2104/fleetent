"""add agent versions, channel_agents, and version-binding columns

Revision ID: 027
Revises: 026
Create Date: 2026-06-02

Owner module: multi-agent-management
"""

import sqlalchemy as sa
from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
        sa.UniqueConstraint("agent_id", "version"),
    )
    op.create_index("idx_agent_versions_agent", "agent_versions", ["agent_id"])

    # channel_agents was previously created only by the legacy agent_store._init_db();
    # adopt it into Alembic so schema lifecycle is migration-owned.
    op.create_table(
        "channel_agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("bound_version_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("platform", "channel_id"),
    )

    op.add_column("agents", sa.Column("active_version_id", sa.Integer(), nullable=True))

    _backfill_v1_versions()


def _backfill_v1_versions() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, system_prompt, allowed_tools, created_at "
            "FROM agents WHERE active_version_id IS NULL"
        )
    ).fetchall()
    for agent_id, system_prompt, allowed_tools, created_at in rows:
        result = bind.execute(
            sa.text(
                "INSERT INTO agent_versions "
                "(agent_id, version, system_prompt, allowed_tools, skills_dir, "
                " mcp_server_ids, model_overrides, memory_namespace, created_at) "
                "VALUES (:agent_id, 1, :system_prompt, :allowed_tools, NULL, "
                " NULL, '{}', 'default', :created_at)"
            ),
            {
                "agent_id": agent_id,
                "system_prompt": system_prompt,
                "allowed_tools": allowed_tools,
                "created_at": created_at,
            },
        )
        version_id = result.lastrowid
        bind.execute(
            sa.text("UPDATE agents SET active_version_id = :vid WHERE id = :aid"),
            {"vid": version_id, "aid": agent_id},
        )


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch_op:
        batch_op.drop_column("active_version_id")
    op.drop_table("channel_agents")
    op.drop_index("idx_agent_versions_agent", table_name="agent_versions")
    op.drop_table("agent_versions")
