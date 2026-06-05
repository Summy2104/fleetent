"""add im_users.meta_json — per-platform identity metadata

A nullable JSON text blob holding admin-editable, platform-specific attributes of
an IM identity (e.g. Slack display name / email / team id, Telegram username /
phone). The platform handle (platform, platform_user_id) is auto-captured from the
gateway and stays read-only; only this metadata is editable. Nullable; legacy rows
default to an empty object in the store.

Revision ID: 048
Revises: 047
Create Date: 2026-06-05

Owner module: im-gateway-management
"""

import sqlalchemy as sa
from alembic import op

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("im_users", sa.Column("meta_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("im_users", "meta_json")
