"""add traces table

Revision ID: 003
Revises: 002
Create Date: 2026-05-31
"""

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("idx_traces_tenant_event_ts", table_name="traces")
    op.drop_index("idx_traces_agent_ts", table_name="traces")
    op.drop_index("idx_traces_user_ts", table_name="traces")
    op.drop_index("idx_traces_run_id", table_name="traces")
    op.drop_table("traces")
