"""add agent plugins column

AR7 (plugin-tools). Existing production databases gain the agents.plugins column
via this alembic migration. Re-chained onto 032 during the next<-main integration;
alembic is the single source of schema truth (no inline _init_db).

Revision ID: 033
Revises: 032
Create Date: 2026-06-03
"""

import sqlalchemy as sa
from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("plugins", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("agents", "plugins")
