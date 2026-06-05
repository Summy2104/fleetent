"""add agents.icon — per-agent avatar emoji

An optional short string (emoji) shown as the agent's avatar in the console.
Agent-level identity, not versioned. Nullable; legacy rows fall back to a default
icon in the UI.

Revision ID: 047
Revises: 046
Create Date: 2026-06-05

Owner module: agent-management-console
"""

import sqlalchemy as sa
from alembic import op

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("icon", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "icon")
