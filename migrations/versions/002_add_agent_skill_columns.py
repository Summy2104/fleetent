"""add agent skill binding columns

Revision ID: 002
Revises: 001
Create Date: 2026-05-31
"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: NULL = agent did not declare allowed_skills (opt-in → no skill
    # injected); distinct from an empty-list "explicitly allow nothing".
    op.add_column("agents", sa.Column("allowed_skills", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("blocked_skills", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "blocked_skills")
    op.drop_column("agents", "allowed_skills")
