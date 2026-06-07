"""add agent_secrets table — encrypted inject-mode credential values

Stores per-agent secret values for credential slots whose mode is ``inject`` (the
platform writes the real value into the materialized ``.env``). Values are encrypted
at rest with a symmetric key from the ``FLEETENT_SECRET_KEY`` process env — never stored
in plaintext, no external KMS. operator-mode slots keep zero platform-held secrets.

Revision ID: 053
Revises: 053
Create Date: 2026-06-05

Owner module: secret-management
"""

import sqlalchemy as sa
from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_secrets",
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("env_name", sa.Text(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("agent_id", "env_name"),
    )


def downgrade() -> None:
    op.drop_table("agent_secrets")
