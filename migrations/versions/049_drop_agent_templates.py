"""drop agent templates — remove the template module

The agent console no longer scaffolds from templates: creating an agent never
required one in practice and the management UI was removed. Drop the editable
``agent_templates`` table (migration 034) and the dormant ``agent_versions.template_id``
column (migration 035). Downgrade recreates both, reseeding the built-ins.

Revision ID: 049
Revises: 048
Create Date: 2026-06-05

Owner module: agent-management-console
"""

import json
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None

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
    with op.batch_alter_table("agent_versions") as batch_op:
        batch_op.drop_column("template_id")
    op.drop_table("agent_templates")


def downgrade() -> None:
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
    with op.batch_alter_table("agent_versions") as batch_op:
        batch_op.add_column(sa.Column("template_id", sa.Text(), nullable=True))
