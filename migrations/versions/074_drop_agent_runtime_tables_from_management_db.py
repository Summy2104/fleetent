"""drop agent runtime tables from management DB

Revision ID: 074
Revises: 073
Create Date: 2026-06-11

Owner module: runtime/agent_state_migrations.py (agent-side, per-agent agent_state.db)

The traces, memory_items, and reflection_reports tables are now owned
exclusively by the per-agent agent_state.db via embedded Y migrations.
This migration completes dual-authority cleanup by dropping the orphaned
management-DB definitions.
"""

import sqlalchemy as sa
from alembic import op

revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("reflection_reports")
    op.drop_table("memory_items")
    op.drop_table("traces")


def downgrade() -> None:
    op.create_table(
        "traces",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("span_id", sa.Text(), nullable=True),
        sa.Column("parent_span_id", sa.Text(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("agent_id", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Text(), nullable=False, server_default="default"),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )
    op.create_index("idx_traces_run_id", "traces", ["run_id"])
    op.create_index("idx_traces_user_ts", "traces", ["user_id", "ts"])
    op.create_index("idx_traces_agent_ts", "traces", ["agent_id", "ts"])
    op.create_index("idx_traces_tenant_event_ts", "traces", ["tenant_id", "event_type", "ts"])

    op.create_table(
        "memory_items",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_memory_items_user_type", "memory_items", ["user_id", "type"])
    op.create_index("idx_memory_items_user_expires", "memory_items", ["user_id", "expires_at"])

    op.create_table(
        "reflection_reports",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("time_window_start", sa.DateTime(), nullable=False),
        sa.Column("time_window_end", sa.DateTime(), nullable=False),
        sa.Column("findings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_reflection_reports_scope_created",
        "reflection_reports",
        ["scope", "created_at"],
    )
