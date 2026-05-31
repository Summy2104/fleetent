"""add agent plugins column

AR7 (plugin-tools). Per the zy override (mirroring SB3/002): existing production
databases gain the agents.plugins column via this alembic migration rather than a
runtime PRAGMA+ALTER in agent_store._init_db. Fresh / test databases get the
column inline from _init_db's CREATE TABLE. NEEDS 张亮 review (agent_store /
agents-table neighbour).

Revision ID: 003
Revises: 002
Create Date: 2026-06-01
"""

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("plugins", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("agents", "plugins")
