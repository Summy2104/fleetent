"""drop invites table (invite_store dead code cleanup)

Revision ID: 064
Revises: 063
Create Date: 2026-06-09

The invites table was created at runtime by invite_store._init_db() (never in alembic).
invite_store is v1-descoped: the feature was never wired to a production route, did not
send emails, and duplicates admin-provisioned users. Drop on upgrade so any deployment
that ran the invite_store code gets cleaned up.
"""

import sqlalchemy as sa
from alembic import op

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("invites", if_exists=True)


def downgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("used_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
