"""drop KB tables from management DB

Revision ID: 076
Revises: 075
Create Date: 2026-06-11

Owner module: knowledge_base/core/migrations.py (tenant-side, per-tenant kb.db)

KB relation and vector state now live exclusively in per-tenant kb.db and
kb_vectors.db. This migration removes the orphaned management-DB copies.
"""

import sqlalchemy as sa
from alembic import op

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("kb_relations")
    op.drop_table("kb_entity_mentions")
    op.drop_table("kb_entities")
    op.drop_table("kb_extraction_runs")
    op.drop_table("knowledge_connector_status")
    op.drop_table("knowledge_chunks_fts")
    op.drop_table("knowledge_source_states")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_bases")


def downgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "kb_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_knowledge_bases_tenant_id",
        ),
    )
    op.create_index("idx_knowledge_bases_archive", "knowledge_bases", ["tenant_id", "archived_at"])

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_knowledge_documents_scope", "knowledge_documents", ["tenant_id", "kb_id"])
    op.create_index(
        "idx_knowledge_documents_archive",
        "knowledge_documents",
        ["tenant_id", "kb_id", "archived_at"],
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_knowledge_chunks_document_position",
        "knowledge_chunks",
        ["document_id", "position"],
    )
    op.create_index("idx_knowledge_chunks_scope", "knowledge_chunks", ["tenant_id", "kb_id"])
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

    op.create_table(
        "knowledge_source_states",
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("mtime_ns", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("source_id", "tenant_id", "kb_id", "source_path"),
    )

    op.create_table(
        "knowledge_connector_status",
        sa.Column("connector_id", sa.Text(), primary_key=True),
        sa.Column("connector_type", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("last_status", sa.Text(), nullable=False),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(), nullable=True),
        sa.Column("last_summary_json", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

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
    op.create_index(
        "idx_kb_entity_mentions_document",
        "kb_entity_mentions",
        ["tenant_id", "kb_id", "document_id"],
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
        "idx_kb_relations_document",
        "kb_relations",
        ["tenant_id", "kb_id", "evidence_document_id"],
    )
