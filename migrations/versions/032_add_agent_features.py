"""add agent features column

Per the zy override (SB3): existing production databases gain the agents.features
column via this alembic migration. Re-chained onto main's trunk (head 031) during
the next<-main architecture integration; alembic is the single source of schema
truth (no inline _init_db).

Revision ID: 032
Revises: 031
Create Date: 2026-06-03
"""

import sqlalchemy as sa
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("features", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "features")
