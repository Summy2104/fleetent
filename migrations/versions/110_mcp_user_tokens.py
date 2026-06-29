"""mcp per-user oauth tokens + pending-auth (managed slice 2)

Revision ID: 110
Revises: 109
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "110"
down_revision = "109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Management-DB per-user MCP OAuth tokens, isolated by the (user_id, agent_id, server_id)
    # triple. access/refresh tokens are stored as Fernet ciphertext (never plaintext). agent_id
    # is TEXT to match the runtime triple semantics (the agent passes its id as a string), not an
    # FK — the token survives independent of registry typing. refresh_token never leaves platform.
    op.create_table(
        "mcp_user_tokens",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("agent_id", sa.Text(), primary_key=True),
        sa.Column("server_id", sa.Text(), primary_key=True),
        sa.Column("access_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("refresh_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.Float(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        # OAuth config carried with the token so transparent refresh is self-contained
        # (no registry round-trip / agent_id-typing dance). client_secret_env is a secret
        # env reference name, never a secret value.
        sa.Column("token_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("client_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("client_secret_env", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    # Short-TTL, one-time pending-auth: the agent registers state -> (PKCE verifier, triple,
    # token endpoint/client) before sending the authorization link, so the platform callback can
    # reverse-resolve and complete the code exchange. code_verifier stored as ciphertext.
    op.create_table(
        "mcp_oauth_pending",
        sa.Column("state", sa.Text(), primary_key=True),
        sa.Column("code_verifier_ciphertext", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("server_id", sa.Text(), nullable=False),
        sa.Column("token_url", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_secret_env", sa.Text(), nullable=False, server_default=""),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("created_at_epoch", sa.Float(), nullable=False),
        sa.Column("consumed", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("mcp_oauth_pending")
    op.drop_table("mcp_user_tokens")
