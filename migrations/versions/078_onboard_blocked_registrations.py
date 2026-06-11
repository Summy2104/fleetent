"""onboard blocked_registrations into alembic

Revision ID: 078
Revises: 077
Create Date: 2026-06-11

Owner module: governance/blocklist.py

This table may already exist on deployed instances because blocklist.py used to
create it lazily at runtime. The migration must therefore preserve any existing
rows and no-op when the table is already present.
"""

import sqlalchemy as sa
from alembic import op

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("blocked_registrations"):
        return

    op.create_table(
        "blocked_registrations",
        sa.Column("email", sa.Text(), primary_key=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("batch_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("blocked_registrations")
