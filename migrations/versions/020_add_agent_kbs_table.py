"""add agent_kbs binding table

Revision ID: 012
Revises: 011
Create Date: 2026-06-02

Owner module: platform / knowledge-base-management

Only the KB↔Agent binding is owned here. KB / document / chunk main tables and any
archive column belong to the knowledge-base engine domain (migrations 006-009).
"""

import sqlalchemy as sa
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_kbs",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "kb_id", "agent_id"),
    )
    op.create_index("idx_agent_kbs_agent", "agent_kbs", ["tenant_id", "agent_id"])


def downgrade() -> None:
    op.drop_index("idx_agent_kbs_agent", table_name="agent_kbs")
    op.drop_table("agent_kbs")
