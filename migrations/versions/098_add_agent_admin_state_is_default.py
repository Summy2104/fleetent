"""add is_default to agent_admin_state

Revision ID: 098
Revises: 097
Create Date: 2026-06-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "098"
down_revision = "097"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_table("agent_admin_state"):
        return
    if "is_default" in _column_names("agent_admin_state"):
        return
    op.add_column(
        "agent_admin_state",
        sa.Column("is_default", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    if not _has_table("agent_admin_state"):
        return
    if "is_default" not in _column_names("agent_admin_state"):
        return
    op.drop_column("agent_admin_state", "is_default")
