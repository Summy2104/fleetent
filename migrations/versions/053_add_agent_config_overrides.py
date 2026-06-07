"""add agents.config_overrides — per-agent agent.yaml field overrides

A JSON blob of agent.yaml fields the operator overrides (governance / deployment /
intelligence / access / connectors / knowledge policy …). Deep-merged onto the
materialized AgentFile defaults so any field is configurable without a column per knob.
Agent-level (not versioned), like icon/tenant_id.

Revision ID: 053
Revises: 052
Create Date: 2026-06-07

Owner module: agent-store / platform-agent-lifecycle
"""

import sqlalchemy as sa
from alembic import op

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("config_overrides", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("agents", "config_overrides")
