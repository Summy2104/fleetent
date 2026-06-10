"""drop platform scheduled_tasks table (agent-owned-scheduled-tasks)

Scheduled tasks are now agent-runtime-owned: each agent process creates the table in
its own DB via schedule_store.ensure_schema and fires/delivers its own tasks. The
platform server no longer loads or fires scheduled tasks (server cron, the stats-report
stub, and the admin-CLI schedule commands were removed), so the management DB no longer
needs this table. scheduled_tasks becomes a pure agent-side table (like `sessions`),
created only by ensure_schema — the drift guard skips tables with no Alembic counterpart.

Revision ID: 067
Revises: 066
Create Date: 2026-06-10
"""

import sqlalchemy as sa
from alembic import op

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("scheduled_tasks")


def downgrade() -> None:
    # Recreate the table as it stood after migration 042 (002 base + session_id).
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("cron_expr", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="UTC"),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source", sa.Text(), nullable=False, server_default="dynamic"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=True),
    )
