"""mcp auth config

Revision ID: 109
Revises: 108
Create Date: 2026-06-29
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "109"
down_revision = "108"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _backfill_auth_config_from_api_key_env() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, auth_type, api_key_env FROM mcp_servers ORDER BY id")
    ).mappings()
    for row in rows:
        auth_config: dict[str, str] = {}
        if row["auth_type"] == "api_key" and row["api_key_env"]:
            auth_config["key_env"] = row["api_key_env"]
        bind.execute(
            sa.text("UPDATE mcp_servers SET auth_config = :auth_config WHERE id = :id"),
            {"id": row["id"], "auth_config": json.dumps(auth_config)},
        )


def _backfill_api_key_env_from_auth_config() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, auth_type, auth_config FROM mcp_servers ORDER BY id")
    ).mappings()
    for row in rows:
        api_key_env = ""
        if row["auth_type"] == "api_key" and row["auth_config"]:
            parsed = json.loads(row["auth_config"])
            if isinstance(parsed, dict):
                value = parsed.get("key_env")
                if isinstance(value, str):
                    api_key_env = value
        bind.execute(
            sa.text("UPDATE mcp_servers SET api_key_env = :api_key_env WHERE id = :id"),
            {"id": row["id"], "api_key_env": api_key_env},
        )


def upgrade() -> None:
    if not _has_table("mcp_servers"):
        return
    op.add_column("mcp_servers", sa.Column("auth_config", sa.JSON(), nullable=True))
    _backfill_auth_config_from_api_key_env()
    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.drop_column("api_key_env")


def downgrade() -> None:
    if not _has_table("mcp_servers"):
        return
    op.add_column(
        "mcp_servers", sa.Column("api_key_env", sa.Text(), nullable=False, server_default="")
    )
    _backfill_api_key_env_from_auth_config()
    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.drop_column("auth_config")
