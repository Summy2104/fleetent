"""Add resync_epoch column to agent_skills.

A backflow decision (accept/reject/fork) bumps this per-binding counter so the
owning node force-redeploys the skill once, returning a drifted home copy to the
pool head and clearing the drift that would otherwise re-trigger nomination.

Revision ID: 103
Revises: 102
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "103"
down_revision = "102"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    return column in cols


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("agent_skills"):
        return
    if not _has_column("agent_skills", "resync_epoch"):
        op.add_column(
            "agent_skills",
            sa.Column("resync_epoch", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if not _has_table("agent_skills"):
        return
    if _has_column("agent_skills", "resync_epoch"):
        op.drop_column("agent_skills", "resync_epoch")
