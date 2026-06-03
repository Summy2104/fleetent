"""add agent allowed_skills column

agent-skill-scoping. Existing production databases gain the agents.allowed_skills
column via this alembic migration. Empty ([]) means no skill-catalog narrowing —
backward compatible. Re-chained onto 033 during the next<-main integration;
alembic is the single source of schema truth (no inline _init_db).

Revision ID: 034
Revises: 033
Create Date: 2026-06-03
"""

import sqlalchemy as sa
from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("allowed_skills", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("agents", "allowed_skills")
