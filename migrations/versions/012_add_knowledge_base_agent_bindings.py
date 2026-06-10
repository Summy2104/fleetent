"""add knowledge base agent bindings

Revision ID: 012
Revises: 011
Create Date: 2026-06-02

Owner module: knowledge-base
"""

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None
_TABLE = "knowledge_base_agent_bindings"
_INDEX = "idx_knowledge_base_agent_bindings_agent"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "agent_id", "kb_id"),
    )
    op.create_index(
        _INDEX,
        _TABLE,
        ["tenant_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_index(
        _INDEX,
        table_name=_TABLE,
    )
    op.drop_table(_TABLE)
