"""add agent-owned scheduled_tasks fields (agent-owned-scheduled-tasks)

Adds the schedule-kind / one-shot / interval / delivery / runtime-state columns so
the platform-managed table matches schedule_store.ensure_schema (drift guard). The
agent-side DB creates the same columns via ensure_schema; this keeps the Alembic head
in sync. agent_name is retained (used by the platform stats-report scheduler).

Revision ID: 067
Revises: 066
Create Date: 2026-06-09
"""

import sqlalchemy as sa
from alembic import op

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None

_NEW_COLUMNS = [
    ("schedule_kind", sa.Text(), "cron"),
    ("run_at", sa.Text(), None),
    ("interval_seconds", sa.Integer(), None),
    ("anchor", sa.Text(), None),
    ("origin", sa.Text(), None),
    ("deliver", sa.Text(), None),
    ("last_run_at", sa.Text(), None),
    ("last_status", sa.Text(), None),
    ("last_error", sa.Text(), None),
    ("next_run_at", sa.Text(), None),
]


def upgrade() -> None:
    for name, type_, default in _NEW_COLUMNS:
        kwargs = {"nullable": True}
        if default is not None:
            kwargs["server_default"] = default
        op.add_column("scheduled_tasks", sa.Column(name, type_, **kwargs))


def downgrade() -> None:
    for name, _type, _default in reversed(_NEW_COLUMNS):
        op.drop_column("scheduled_tasks", name)
