"""widen agent_secrets to a shared (cross-agent) scope

Provider and connector credentials are shared across agents — their inline values
cannot key to a single ``agent_id``. Make ``agent_id`` nullable (NULL = shared scope),
drop the FK + ``(agent_id, env_name)`` primary key, and add a unique expression index on
``(COALESCE(agent_id, -1), env_name)`` so a shared slot and a per-agent slot of the same
env name can coexist. materialize resolves per-agent first, then falls back to shared.

Revision ID: 062
Revises: 061
Create Date: 2026-06-08

Owner module: agent-lifecycle / secret-store
"""

import sqlalchemy as sa
from alembic import op

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("agent_secrets", "agent_secrets_old")
    op.create_table(
        "agent_secrets",
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("env_name", sa.Text(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=True),
    )
    op.execute(
        "INSERT INTO agent_secrets (agent_id, env_name, ciphertext, updated_at, updated_by) "
        "SELECT agent_id, env_name, ciphertext, updated_at, updated_by FROM agent_secrets_old"
    )
    op.drop_table("agent_secrets_old")
    op.create_index(
        "ux_agent_secrets_scope",
        "agent_secrets",
        [sa.text("COALESCE(agent_id, -1)"), "env_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_agent_secrets_scope", table_name="agent_secrets")
    op.execute("DELETE FROM agent_secrets WHERE agent_id IS NULL")
    op.rename_table("agent_secrets", "agent_secrets_old")
    op.create_table(
        "agent_secrets",
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("env_name", sa.Text(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id", "env_name"),
    )
    op.execute(
        "INSERT INTO agent_secrets (agent_id, env_name, ciphertext, updated_at, updated_by) "
        "SELECT agent_id, env_name, ciphertext, updated_at, updated_by FROM agent_secrets_old"
    )
    op.drop_table("agent_secrets_old")
