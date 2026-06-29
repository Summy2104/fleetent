"""retire platform-managed KB ingest tables

Revision ID: 111
Revises: 110
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "111"
down_revision = "110"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_index(table: str, index: str) -> bool:
    return any(item["name"] == index for item in sa.inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    if _has_table("kb_ingest_jobs") and _has_index(
        "kb_ingest_jobs", "ix_kb_ingest_jobs_status_created_at"
    ):
        op.drop_index("ix_kb_ingest_jobs_status_created_at", table_name="kb_ingest_jobs")
    if _has_table("kb_connector_schedule_state"):
        op.drop_table("kb_connector_schedule_state")
    if _has_table("kb_ingest_jobs"):
        op.drop_table("kb_ingest_jobs")
    if _has_table("kb_connectors"):
        op.drop_table("kb_connectors")


def downgrade() -> None:
    if not _has_table("kb_connectors"):
        op.create_table(
            "kb_connectors",
            sa.Column("connector_id", sa.Text(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("kb_id", sa.Text(), nullable=False),
            sa.Column("config", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.Column("custom", sa.Text(), nullable=True),
            sa.Column("sync_interval_seconds", sa.Integer(), nullable=True),
            sa.Column("last_scheduled_sync_at", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("connector_id"),
        )
    if not _has_table("kb_ingest_jobs"):
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
    if not _has_index("kb_ingest_jobs", "ix_kb_ingest_jobs_status_created_at"):
        op.create_index(
            "ix_kb_ingest_jobs_status_created_at",
            "kb_ingest_jobs",
            ["status", "created_at"],
            unique=False,
        )
    if not _has_table("kb_connector_schedule_state"):
        op.create_table(
            "kb_connector_schedule_state",
            sa.Column("connector_id", sa.Text(), nullable=False),
            sa.Column("last_scheduled_sync_at", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("connector_id"),
        )
