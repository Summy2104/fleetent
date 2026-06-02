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


def upgrade() -> None:
    op.create_table(
        "knowledge_base_agent_bindings",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "agent_id", "kb_id"),
    )
    op.create_index(
        "idx_knowledge_base_agent_bindings_agent",
        "knowledge_base_agent_bindings",
        ["tenant_id", "agent_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_knowledge_base_agent_bindings_agent",
        table_name="knowledge_base_agent_bindings",
    )
    op.drop_table("knowledge_base_agent_bindings")
