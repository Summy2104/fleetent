"""Add shared memory items table.

Revision ID: 029
Revises: 028
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shared_memory_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index(
        "idx_shared_memory_scope_status",
        "shared_memory_items",
        ["scope_type", "scope_id", "status"],
    )
    op.create_index(
        "idx_shared_memory_source_ref",
        "shared_memory_items",
        ["source", "source_ref"],
    )


def downgrade() -> None:
    op.drop_index("idx_shared_memory_source_ref", table_name="shared_memory_items")
    op.drop_index("idx_shared_memory_scope_status", table_name="shared_memory_items")
    op.drop_table("shared_memory_items")
