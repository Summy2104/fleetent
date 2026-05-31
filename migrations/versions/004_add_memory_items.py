"""add memory items table

Revision ID: 004
Revises: 003
Create Date: 2026-05-31
"""

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_items",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_memory_items_user_type", "memory_items", ["user_id", "type"])
    op.create_index("idx_memory_items_user_expires", "memory_items", ["user_id", "expires_at"])


def downgrade() -> None:
    op.drop_index("idx_memory_items_user_expires", table_name="memory_items")
    op.drop_index("idx_memory_items_user_type", table_name="memory_items")
    op.drop_table("memory_items")
