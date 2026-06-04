"""add knowledge-base metadata fields

Revision ID: 046
Revises: 045
Create Date: 2026-06-04

Owner module: knowledge-base
"""

import sqlalchemy as sa
from alembic import op

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "knowledge_bases",
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "idx_knowledge_bases_archive",
        "knowledge_bases",
        ["tenant_id", "archived_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_bases_archive", table_name="knowledge_bases")
    op.drop_column("knowledge_bases", "archived_at")
    op.drop_column("knowledge_bases", "description")
