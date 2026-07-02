"""add skill_git_source table (external git source config + sync state)

Revision ID: 115
Revises: 114
Create Date: 2026-06-30

Owner module: platform / skill_management (skill-gitops-inbound)

Single-row (id='default') config store binding the skill pool to an external git
repo as authoritative source: provider / url / branch, credential env-ref names,
sync interval, and last-sync state. branch_prefix / auto_open_pr are consumed by the
later outbound backflow change; kept here so the unified config table is built once.
Credentials themselves live in agent_secrets (env-ref), never in this table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "115"
down_revision = "114"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table("skill_git_source"):
        return
    op.create_table(
        "skill_git_source",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider", sa.Text(), nullable=False, server_default="bitbucket"),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("project", sa.Text(), nullable=True),
        sa.Column("repo", sa.Text(), nullable=True),
        sa.Column("remote_url", sa.Text(), nullable=True),
        sa.Column("branch", sa.Text(), nullable=False, server_default="main"),
        sa.Column("branch_prefix", sa.Text(), nullable=False, server_default="backflow"),
        sa.Column("auto_open_pr", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("username_env", sa.Text(), nullable=True),
        sa.Column("token_env", sa.Text(), nullable=True),
        sa.Column("webhook_secret_env", sa.Text(), nullable=True),
        sa.Column("sync_interval_seconds", sa.Integer(), nullable=True),
        sa.Column("last_synced_commit", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.Text(), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("skill_git_source")
