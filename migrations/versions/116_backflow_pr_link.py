"""Add PR-link columns to backflow_proposals for the outbound git-PR backflow.

The outbound backflow sweep pushes a backup branch then opens a PR; these nullable
columns track that lifecycle per proposal (branch name, PR id/url, normalised state,
target branch, merge commit). Old proposals (pr_* = NULL) are treated as not-yet-backed-up
and picked up by the sweep.

Revision ID: 116
Revises: 115
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "116"
down_revision = "115"
branch_labels = None
depends_on = None

_TABLE = "backflow_proposals"
_COLUMNS = ("pr_id", "pr_branch", "pr_url", "pr_state", "pr_target_branch", "pr_merge_commit")
_INDEX = "idx_backflow_proposals_pr_state"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_index(table: str, name: str) -> bool:
    return name in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if not _has_table(_TABLE):
        return
    for column in _COLUMNS:
        if not _has_column(_TABLE, column):
            op.add_column(_TABLE, sa.Column(column, sa.Text(), nullable=True))
    if not _has_index(_TABLE, _INDEX):
        op.create_index(_INDEX, _TABLE, ["pr_state"])


def downgrade() -> None:
    if not _has_table(_TABLE):
        return
    if _has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
    for column in _COLUMNS:
        if _has_column(_TABLE, column):
            op.drop_column(_TABLE, column)
