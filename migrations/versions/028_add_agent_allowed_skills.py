"""add agent allowed_skills column

agent-skill-scoping. Per the zy override (mirroring 002/003): existing production
databases gain the agents.allowed_skills column via this alembic migration rather
than a runtime PRAGMA+ALTER in agent_store._init_db. Fresh / test databases get the
column inline from _init_db's CREATE TABLE. Empty ([]) means no skill-catalog
narrowing — backward compatible (all enabled skills remain visible).

Revision ID: 004
Revises: 003
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("allowed_skills", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("agents", "allowed_skills")
