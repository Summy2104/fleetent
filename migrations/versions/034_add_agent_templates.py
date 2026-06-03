"""add agent_templates table seeded with built-in templates

Revision ID: 034
Revises: 033
Create Date: 2026-06-03

Owner module: agent_management_console
"""

import json
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


# Seed values mirror the original agent_templates.py module constants.
_SEED = [
    {
        "id": "readonly-qa",
        "display_name": "只读问答 Agent",
        "allowed_tools": ["read_*", "search_*"],
        "system_prompt": "You are a read-only question-answering assistant. "
        "Answer from available knowledge and never perform write or destructive actions.",
    },
    {
        "id": "ops",
        "display_name": "运维 Agent",
        "allowed_tools": ["read_*", "exec_*", "github__*"],
        "system_prompt": "You are an operations assistant. Help diagnose and operate systems; "
        "request approval before any high-risk action.",
    },
    {
        "id": "support",
        "display_name": "客服 Agent",
        "allowed_tools": ["read_*", "search_*", "ticket__*"],
        "system_prompt": "You are a customer-support assistant. Be empathetic, accurate, "
        "and escalate to a human when unsure.",
    },
]


def upgrade() -> None:
    templates = op.create_table(
        "agent_templates",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("allowed_tools", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    now = datetime.now(UTC).isoformat()
    op.bulk_insert(
        templates,
        [
            {
                "id": t["id"],
                "display_name": t["display_name"],
                "allowed_tools": json.dumps(t["allowed_tools"]),
                "system_prompt": t["system_prompt"],
                "created_at": now,
                "updated_at": now,
            }
            for t in _SEED
        ],
    )


def downgrade() -> None:
    op.drop_table("agent_templates")
