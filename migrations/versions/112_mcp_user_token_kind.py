"""mcp_user_tokens credential_kind (per-user api-key/bearer)

Revision ID: 112
Revises: 111
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "112"
down_revision = "111"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # Make the per-user credential store type-aware: existing rows are OAuth tokens
    # (default/backfill 'oauth'); per-user api-key/bearer rows store 'static' (only the
    # injected secret in access_token_ciphertext, OAuth columns NULL).
    if not _has_table("mcp_user_tokens"):
        return
    op.add_column(
        "mcp_user_tokens",
        sa.Column("credential_kind", sa.Text(), nullable=False, server_default="oauth"),
    )


def downgrade() -> None:
    if not _has_table("mcp_user_tokens"):
        return
    with op.batch_alter_table("mcp_user_tokens") as batch_op:
        batch_op.drop_column("credential_kind")
