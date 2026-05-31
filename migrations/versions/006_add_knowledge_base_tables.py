"""add knowledge-base tables

Revision ID: 006
Revises: 005
Create Date: 2026-06-01

Owner module: knowledge-base
"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "kb_id"),
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "kb_id"],
            ["knowledge_bases.tenant_id", "knowledge_bases.kb_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_knowledge_documents_scope",
        "knowledge_documents",
        ["tenant_id", "kb_id"],
    )
    op.create_index(
        "idx_knowledge_chunks_document_position",
        "knowledge_chunks",
        ["document_id", "position"],
    )
    op.create_index(
        "idx_knowledge_chunks_scope",
        "knowledge_chunks",
        ["tenant_id", "kb_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_knowledge_chunks_scope", table_name="knowledge_chunks")
    op.drop_index("idx_knowledge_chunks_document_position", table_name="knowledge_chunks")
    op.drop_index("idx_knowledge_documents_scope", table_name="knowledge_documents")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_bases")
