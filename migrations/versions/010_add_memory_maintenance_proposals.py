"""add memory maintenance proposals

Revision ID: 010
Revises: 009
Create Date: 2026-06-02

Owner module: reflection
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index(
        "idx_memory_maintenance_user_status",
        table_name="memory_maintenance_proposals",
    )
    op.drop_table("memory_maintenance_proposals")
