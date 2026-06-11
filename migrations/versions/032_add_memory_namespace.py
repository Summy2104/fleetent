"""add namespace column to memory_items

Revision ID: 032
Revises: 031
Create Date: 2026-06-02

Owner module: multi-agent-management
"""

import sqlalchemy as sa
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def _has_memory_items_table() -> bool:
    return sa.inspect(op.get_bind()).has_table("memory_items")


def _has_memory_items_index(name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == name for index in inspector.get_indexes("memory_items"))


def _has_memory_items_column(name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == name for column in inspector.get_columns("memory_items"))


def upgrade() -> None:
    op.add_column(
        "memory_items",
        sa.Column("namespace", sa.Text(), nullable=False, server_default="default"),
    )
    op.create_index(
        "idx_memory_items_user_namespace_type",
        "memory_items",
        ["user_id", "namespace", "type"],
    )


def downgrade() -> None:
    if not _has_memory_items_table():
        return
    if _has_memory_items_index("idx_memory_items_user_namespace_type"):
        op.drop_index("idx_memory_items_user_namespace_type", table_name="memory_items")
    if _has_memory_items_column("namespace"):
        with op.batch_alter_table("memory_items") as batch_op:
            batch_op.drop_column("namespace")
