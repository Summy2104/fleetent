"""add askit orchestration console tables

Revision ID: 017
Revises: 016
Create Date: 2026-06-02

Owner module: platform / askit-orchestration-console

Async task tracking + streamed logs + git-backed workspaces for the askit console.
askit itself is an external tool invoked as a subprocess; only orchestration state is
persisted here. Sensitive values in params/logs are masked before persisting.
"""

import sqlalchemy as sa
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("idx_askit_task_logs", table_name="askit_task_logs")
    op.drop_table("askit_task_logs")
    op.drop_table("askit_tasks")
    op.drop_table("askit_workspaces")
