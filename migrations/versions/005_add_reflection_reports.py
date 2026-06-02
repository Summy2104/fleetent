"""add reflection reports table

Revision ID: 005
Revises: 004
Create Date: 2026-05-31
"""

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reflection_reports",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("time_window_start", sa.DateTime(), nullable=False),
        sa.Column("time_window_end", sa.DateTime(), nullable=False),
        sa.Column("findings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_reflection_reports_scope_created",
        "reflection_reports",
        ["scope", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_reflection_reports_scope_created", table_name="reflection_reports")
    op.drop_table("reflection_reports")
