"""add resource monitoring + alerting tables

Revision ID: 016
Revises: 015
Create Date: 2026-06-02

Owner module: platform / resource-monitoring-alerting

All self-hosted, in-network: a lightweight local time-series table plus alert rules,
alerts, and maintenance windows. Channel credentials are never stored here (env +
masking). No cloud APM / SaaS time-series.
"""

import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_samples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("ts", sa.Text(), nullable=False),
    )
    op.create_index("idx_metric_samples_q", "metric_samples", ["metric", "target", "ts"])
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=True),
        sa.Column("comparator", sa.Text(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("for_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("severity", sa.Text(), nullable=False, server_default="warning"),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("channels", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="firing"),
        sa.Column("fired_at", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.Text(), nullable=True),
        sa.Column("acked_by", sa.Text(), nullable=True),
        sa.Column("assignee", sa.Text(), nullable=True),
        sa.Column("snapshot", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_alerts_active", "alerts", ["rule_id", "target", "status"])
    op.create_table(
        "maintenance_windows",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("target", sa.Text(), nullable=True),
        sa.Column("start_ts", sa.Text(), nullable=False),
        sa.Column("end_ts", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("maintenance_windows")
    op.drop_index("idx_alerts_active", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("alert_rules")
    op.drop_index("idx_metric_samples_q", table_name="metric_samples")
    op.drop_table("metric_samples")
