"""add scheduled_tasks.session_id column (S3 cron<->session binding)

Re-grafts zhangyang's S3 feature onto main's db.py-backed scheduler. session_id is
optional (NULL = each fire runs an independent, freshly-derived session; a value =
the task accumulates context in that fixed session across fires). Backward
compatible: existing rows default to NULL. Re-chained onto 037 during the
next<-main integration.

Revision ID: 038
Revises: 037
Create Date: 2026-06-03
"""

import sqlalchemy as sa
from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduled_tasks",
        sa.Column("session_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "session_id")
