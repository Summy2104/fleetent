"""add knowledge-base reflection reports

Revision ID: 027
Revises: 026
Create Date: 2026-06-02

Owner module: intelligence.reflection
"""

import sqlalchemy as sa
from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_reflection_reports",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("time_window_start", sa.Text(), nullable=False),
        sa.Column("time_window_end", sa.Text(), nullable=False),
        sa.Column("findings_json", sa.Text(), nullable=False),
        sa.Column("signal_summary_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_kb_reflection_reports_scope_created",
        "kb_reflection_reports",
        ["scope", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_kb_reflection_reports_scope_created",
        table_name="kb_reflection_reports",
    )
    op.drop_table("kb_reflection_reports")
