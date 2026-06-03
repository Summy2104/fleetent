"""add agent features column

Per the zy override (SB3): existing production databases gain the agents.features
column via this alembic migration rather than a runtime PRAGMA+ALTER in
agent_store._init_db. Fresh / test databases get the column inline from
_init_db's CREATE TABLE. NEEDS 张亮 review (agent_store / agents-table neighbour).

Revision ID: 002
Revises: 001
Create Date: 2026-06-01
"""

import sqlalchemy as sa
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("features", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "features")
