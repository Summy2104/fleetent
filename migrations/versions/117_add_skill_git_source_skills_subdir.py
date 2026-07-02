"""Add skills_subdir to skill_git_source; flip auto_open_pr default 1→0.

Adds nullable skills_subdir TEXT column to skill_git_source table, allowing config
to point at a subdirectory of an external git repo (e.g. 'skills/' in a monorepo)
instead of assuming the repo root is the skill directory. NULL preserves existing
behavior (repo root).

Flips auto_open_pr default from 1 to 0 and backtracks all existing rows from 1→0.
The auto_open_pr=1 feature (auto open PR on backflow) has not shipped to any real
deployment yet, so rewriting historical rows is safe and cleaner than leaving them
at the old default.

Revision ID: 117
Revises: 116
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "117"
down_revision = "116"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_table("skill_git_source"):
        return

    # Add skills_subdir column (nullable, defaults NULL)
    if not _has_column("skill_git_source", "skills_subdir"):
        op.add_column("skill_git_source", sa.Column("skills_subdir", sa.Text(), nullable=True))

    # Flip auto_open_pr default from 1 to 0
    with op.batch_alter_table("skill_git_source") as batch_op:
        batch_op.alter_column("auto_open_pr", existing_type=sa.Integer(), server_default="0")

    # Backtrack all existing auto_open_pr=1 rows to 0 (safe: feature never shipped)
    op.execute("UPDATE skill_git_source SET auto_open_pr = 0 WHERE auto_open_pr = 1")


def downgrade() -> None:
    if not _has_table("skill_git_source"):
        return

    # Check if skills_subdir exists before entering batch_alter_table
    has_skills_subdir = _has_column("skill_git_source", "skills_subdir")

    # SQLite requires drop_column inside batch_alter_table
    with op.batch_alter_table("skill_git_source") as batch_op:
        # Drop skills_subdir column if it exists
        if has_skills_subdir:
            batch_op.drop_column("skills_subdir")
        # Restore auto_open_pr default to 1 (but leave backtracked rows at 0)
        batch_op.alter_column("auto_open_pr", existing_type=sa.Integer(), server_default="1")
