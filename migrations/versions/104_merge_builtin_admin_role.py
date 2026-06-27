"""Merge built_in_admin role into admin.

Revision ID: 104
Revises: 103
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "104"
down_revision = "103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE users SET role = 'admin' WHERE role = 'built_in_admin'"))


def downgrade() -> None:
    # Forward-only data migration: once roles are merged, admin is the canonical value.
    pass
