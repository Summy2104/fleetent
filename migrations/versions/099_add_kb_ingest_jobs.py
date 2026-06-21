"""add kb ingest jobs queue

Revision ID: 099
Revises: 098
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "099"
down_revision = "098"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table("kb_ingest_jobs"):
        return
    op.create_table(
        "kb_ingest_jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("kb_id", sa.Text(), nullable=False),
        sa.Column("connector_ref", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("cred_ref", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("claimed_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_kb_ingest_jobs_status_created_at",
        "kb_ingest_jobs",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    if not _has_table("kb_ingest_jobs"):
        return
    op.drop_index("ix_kb_ingest_jobs_status_created_at", table_name="kb_ingest_jobs")
    op.drop_table("kb_ingest_jobs")
