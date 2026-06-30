"""webhook sources (live-webhooks, managed inbound triggers)

Revision ID: 113
Revises: 112
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "113"
down_revision = "112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Management-DB inbound webhook sources (managed mode). Each source routes an inbound
    # POST /webhook/{id} to one agent, run as ``user_id``. The HMAC shared secret is stored as
    # Fernet ciphertext (never plaintext) — the platform inbound edge decrypts it to verify the
    # X-Hub-Signature-256 header. ``reply_target`` (optional) is an internal user_id to DM the
    # run result to; NULL = no-op reply.
    op.create_table(
        "webhook_sources",
        sa.Column("id", sa.Text(), primary_key=True),
        # Target agent referenced by id (FK→agents.id), never by name — management tables
        # store agent relationships by agent_id only (agent-identity guardrail).
        sa.Column(
            "agent_id",
            sa.Integer(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("message_template", sa.Text(), nullable=True),
        sa.Column("reply_target", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("webhook_sources")
