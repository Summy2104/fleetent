"""drop residual management DB tables

Revision ID: 077
Revises: 076
Create Date: 2026-06-11

Owner modules:
- memory/shared_memory_migrations.py
- runtime/agent_state_migrations.py
- observability/trace.py

These management-DB tables are residual copies after the platform/agent storage
split. Their live truth sources already moved elsewhere, so head schema must no
longer create them.
"""

import sqlalchemy as sa
from alembic import op

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("skill_hits")
    op.drop_table("shared_memory_items")
    op.drop_table("skill_proposals")
    op.drop_table("memory_maintenance_proposals")


def downgrade() -> None:
    op.create_table(
        "memory_maintenance_proposals",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_memory_ids_json", sa.Text(), nullable=False),
        sa.Column("proposed_content", sa.Text(), nullable=True),
        sa.Column("metadata_patch_json", sa.Text(), nullable=False),
        sa.Column("risk", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_ids_json", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "idx_memory_maintenance_user_status",
        "memory_maintenance_proposals",
        ["user_id", "status", "updated_at"],
    )

    op.create_table(
        "skill_proposals",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("target_skill", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_refs_json", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.Text(), nullable=False),
        sa.Column("suggested_draft", sa.Text(), nullable=True),
        sa.Column("suggested_diff", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reviewer_user_id", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_skill_proposals_status_updated",
        "skill_proposals",
        ["status", "updated_at"],
    )

    op.create_table(
        "shared_memory_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index(
        "idx_shared_memory_scope_status",
        "shared_memory_items",
        ["scope_type", "scope_id", "status"],
    )
    op.create_index(
        "idx_shared_memory_source_ref",
        "shared_memory_items",
        ["source", "source_ref"],
    )

    op.create_table(
        "skill_hits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("skill_name", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("triggered_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_skill_hits_skill_name", "skill_hits", ["skill_name"])
