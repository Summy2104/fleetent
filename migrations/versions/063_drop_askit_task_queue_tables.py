"""drop askit task-queue tables (dead code cleanup)

Revision ID: 063
Revises: 062
Create Date: 2026-06-09

These three tables were created in migration 025 but have never been referenced
by any .py source. The apply-API model (fleetent-apply-api spec) replaced the
task-queue approach before it shipped; the tables are unreachable dead schema.
"""

import sqlalchemy as sa
from alembic import op

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_askit_task_logs", table_name="askit_task_logs")
    op.drop_table("askit_task_logs")
    op.drop_table("askit_tasks")
    op.drop_table("askit_workspaces")


def downgrade() -> None:
    op.create_table(
        "askit_workspaces",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("env", sa.Text(), nullable=False),
        sa.Column("repo_path", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "askit_tasks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("series", sa.Text(), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("params", sa.Text(), nullable=True),
        sa.Column("workspace", sa.Text(), nullable=True),
        sa.Column("env", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("artifact", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "askit_task_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("stream", sa.Text(), nullable=False),
        sa.Column("line", sa.Text(), nullable=False),
    )
    op.create_index("idx_askit_task_logs", "askit_task_logs", ["task_id", "seq"])
