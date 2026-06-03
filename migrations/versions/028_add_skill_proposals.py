"""add skill reflection proposals

Revision ID: 028
Revises: 027
Create Date: 2026-06-02

Owner module: intelligence.reflection
"""

import sqlalchemy as sa
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("idx_skill_proposals_status_updated", table_name="skill_proposals")
    op.drop_table("skill_proposals")
