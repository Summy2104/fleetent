"""add knowledge-base entity extraction tables

Revision ID: 026
Revises: 025
Create Date: 2026-06-02

Owner module: intelligence.knowledge_base
"""

import sqlalchemy as sa
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_extraction_runs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=True),
        sa.Column("extractor", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("documents_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunks_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("entities_upserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mentions_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relations_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "kb_entities",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "kb_id",
            "entity_type",
            "normalized_name",
            name="uq_kb_entities_scope_type_name",
        ),
    )
    op.create_table(
        "kb_entity_mentions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extraction_run_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "kb_relations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("source_entity_id", sa.Text(), nullable=False),
        sa.Column("target_entity_id", sa.Text(), nullable=False),
        sa.Column("evidence_document_id", sa.Text(), nullable=False),
        sa.Column("evidence_chunk_id", sa.Text(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extraction_run_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_kb_entity_mentions_document",
        "kb_entity_mentions",
        ["tenant_id", "kb_id", "document_id"],
    )
    op.create_index(
        "idx_kb_relations_document",
        "kb_relations",
        ["tenant_id", "kb_id", "evidence_document_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_kb_relations_document", table_name="kb_relations")
    op.drop_index("idx_kb_entity_mentions_document", table_name="kb_entity_mentions")
    op.drop_table("kb_relations")
    op.drop_table("kb_entity_mentions")
    op.drop_table("kb_entities")
    op.drop_table("kb_extraction_runs")
