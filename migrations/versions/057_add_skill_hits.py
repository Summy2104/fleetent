"""add skill_hits table

Revision ID: 057
Revises: 056
Create Date: 2026-06-07

Owner module: platform / skill-management / skill-observability-tracking

Append-only hit stream: one row per successful read_skill load, powering the
per-skill observability view (hit counts + triggering sessions) that previously
returned a stale placeholder.
"""

import sqlalchemy as sa
from alembic import op

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skill_hits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("skill_name", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("triggered_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_skill_hits_skill_name", "skill_hits", ["skill_name"])


def downgrade() -> None:
    op.drop_index("ix_skill_hits_skill_name", table_name="skill_hits")
    op.drop_table("skill_hits")
