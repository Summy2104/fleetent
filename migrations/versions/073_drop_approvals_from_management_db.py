"""drop approvals table from management DB (agent-owned since 3b-4)

Revision ID: 073
Revises: 072
Create Date: 2026-06-10

Owner module: governance/approval_store (agent-side, per-agent agent_state.db)

The approvals table is now owned exclusively by the per-agent agent_state.db
(MIGRATIONS v12 in runtime/agent_state_migrations.py).  The write path moved
to the agent side in change A; this migration completes dual-authority cleanup
by dropping the orphaned management-DB definition.

Safe to drop: approval_store no longer writes to the management DB (uses
set_state_db injection).  Any existing rows in a production management DB
represent pre-3b-4 data that has already been superseded by the agent-side
store; the platform read-projection is deferred to change 3d.
"""

import sqlalchemy as sa
from alembic import op

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("approvals")


def downgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("requester_user_id", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("tool_args", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("approver_actor", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
