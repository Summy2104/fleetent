"""Add agent ownership columns and bring channel_agents into Alembic.

Adds tenant_id / team_id to the agents table so long-term-ctx policy resolution
can read agent ownership, and takes over channel_agents from the legacy
agent_store._init_db() path.

Revision ID: 030
Revises: 029
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("tenant_id", sa.Text(), nullable=False, server_default="default"),
    )
    op.add_column("agents", sa.Column("team_id", sa.Text(), nullable=True))

    inspector = sa.inspect(op.get_bind())
    if "channel_agents" not in inspector.get_table_names():
        op.create_table(
            "channel_agents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("platform", sa.Text(), nullable=False),
            sa.Column("channel_id", sa.Text(), nullable=False),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("platform", "channel_id"),
        )


def downgrade() -> None:
    op.drop_table("channel_agents")
    with op.batch_alter_table("agents") as batch:
        batch.drop_column("team_id")
        batch.drop_column("tenant_id")
