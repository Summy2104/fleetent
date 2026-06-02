"""add agent_admin_state table

Revision ID: 015
Revises: 014
Create Date: 2026-06-02

Owner module: platform / agent-management-console

Lifecycle status + managed/adhoc provenance + drift live in this side table keyed by
agent name, rather than ALTERing the agents main table. This avoids a hard dependency
on the (not-yet-landed) multi-agent-management versioning/deleted_at migration; when
that lands, status/deleted_at can be reconciled. Mirrors skill_admin_state.
"""

import sqlalchemy as sa
from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_admin_state",
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="enabled"),
        sa.Column("provenance", sa.Text(), nullable=False, server_default="adhoc"),
        sa.Column("drift", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived_at", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("agent_name"),
    )


def downgrade() -> None:
    op.drop_table("agent_admin_state")
