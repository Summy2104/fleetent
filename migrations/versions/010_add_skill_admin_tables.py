"""add skill admin tables

Revision ID: 010
Revises: 009
Create Date: 2026-06-02

Owner module: platform / skill-management
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_skills",
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("skill_name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("agent_id", "skill_name"),
    )
    op.create_index("idx_agent_skills_skill", "agent_skills", ["skill_name"])
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


def downgrade() -> None:
    op.drop_table("skill_admin_state")
    op.drop_table("skill_provenance")
    op.drop_index("idx_agent_skills_skill", table_name="agent_skills")
    op.drop_table("agent_skills")
