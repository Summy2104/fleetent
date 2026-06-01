"""add knowledge document archive marker

Revision ID: 011
Revises: 010
Create Date: 2026-06-02

Owner module: knowledge-base
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "idx_knowledge_documents_archive",
        "knowledge_documents",
        ["tenant_id", "kb_id", "archived_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_documents_archive", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "archived_at")
