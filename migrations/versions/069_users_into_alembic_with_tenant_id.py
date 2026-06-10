"""Bring users table into Alembic management; add users.tenant_id.

Prior to this migration users was built by user_store._init_db() outside
Alembic.  This migration:
  1. Creates users with full schema (including tenant_id) on a clean database.
  2. On an existing database (legacy _init_db path): adds any missing extra
     columns then adds tenant_id, backfills 'default', and enforces NOT NULL + FK.

After this migration user_store._init_db() no longer creates the users table.
Deployments must run `alembic upgrade head` before the application starts.

Revision ID: 068
Revises: 067
Create Date: 2026-06-10
"""

import sqlalchemy as sa
from alembic import op

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None

# Extra columns that _init_db used to add via ALTER TABLE IF NOT EXISTS logic.
# We replicate this here so upgrading from a minimal legacy users table works.
_EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("email", "TEXT"),
    ("password_hash", "TEXT"),
    ("role", "TEXT NOT NULL DEFAULT 'viewer'"),
    ("status", "TEXT NOT NULL DEFAULT 'active'"),
    ("must_reset", "INTEGER NOT NULL DEFAULT 0"),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "users" not in inspector.get_table_names():
        # Clean database — create users from scratch with all columns including tenant_id.
        op.create_table(
            "users",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("api_key", sa.Text(), nullable=False, unique=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("email", sa.Text(), nullable=True),
            sa.Column("password_hash", sa.Text(), nullable=True),
            sa.Column("role", sa.Text(), nullable=False, server_default="viewer"),
            sa.Column("status", sa.Text(), nullable=False, server_default="active"),
            sa.Column("must_reset", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "tenant_id",
                sa.Text(),
                sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
                nullable=False,
                server_default="default",
            ),
        )
        return

    # Existing users table — apply any missing extra columns, then add tenant_id.
    existing_cols = {col["name"] for col in inspector.get_columns("users")}

    for col, decl in _EXTRA_COLUMNS:
        if col not in existing_cols:
            bind.execute(sa.text(f"ALTER TABLE users ADD COLUMN {col} {decl}"))

    if "tenant_id" not in existing_cols:
        bind.execute(sa.text("ALTER TABLE users ADD COLUMN tenant_id TEXT"))

    # Backfill: set tenant_id='default' for any row that lacks it.
    op.execute(sa.text("UPDATE users SET tenant_id = 'default' WHERE tenant_id IS NULL"))

    # Recreate table to enforce NOT NULL + FK constraint.
    with op.batch_alter_table("users", recreate="always") as batch_op:
        batch_op.alter_column("tenant_id", existing_type=sa.Text(), nullable=False)
        batch_op.create_foreign_key("fk_users_tenant_id", "tenants", ["tenant_id"], ["id"])


def downgrade() -> None:
    # Drop tenant_id column — batch recreate removes the FK along with it.
    # We do NOT drop the users table: it may have existed before this migration
    # (legacy _init_db path); we only own the tenant_id column we added.
    with op.batch_alter_table("users", recreate="always") as batch_op:
        batch_op.drop_column("tenant_id")
