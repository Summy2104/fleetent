"""add knowledge-base FTS index

Revision ID: 007
Revises: 006
Create Date: 2026-06-01

Owner module: knowledge-base
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE knowledge_chunks_fts
        USING fts5(
            chunk_id UNINDEXED,
            tenant_id UNINDEXED,
            kb_id UNINDEXED,
            content,
            tokenize = 'unicode61'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_chunks_fts")
