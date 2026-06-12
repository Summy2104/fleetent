"""backfill api_keys from users.api_key and drop legacy column

Revision ID: 080
Revises: 079
Create Date: 2026-06-12

Step 1: Hash every non-NULL, non-empty users.api_key value into api_keys
        (scope ["*"], no expiry, INSERT OR IGNORE for idempotency).
Step 2: Drop the users.api_key column (rename+recreate because SQLite lacks
        ALTER TABLE ... DROP COLUMN in older versions).

Downgrade: re-adds the api_key column as nullable (plaintext not restored —
           that is by design; meaningful only within a pre-ship rollback window).
"""

from __future__ import annotations

import datetime
import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Idempotent: if api_key column is already gone, nothing to do.
    col_names = {c["name"] for c in inspector.get_columns("users")}
    if "api_key" not in col_names:
        return

    now = datetime.datetime.now(datetime.UTC).isoformat()

    # Step 1: backfill non-NULL/non-empty plaintext keys into api_keys.
    rows = bind.execute(
        sa.text("SELECT id, api_key FROM users WHERE api_key IS NOT NULL AND api_key != ''")
    ).fetchall()
    for user_id, plaintext in rows:
        bind.execute(
            sa.text(
                "INSERT OR IGNORE INTO api_keys"
                " (user_id, key_hash, prefix, scope, note, created_at, call_count)"
                " VALUES (:user_id, :key_hash, :prefix, :scope, 'migrated', :created_at, 0)"
            ),
            {
                "user_id": user_id,
                "key_hash": _hash(plaintext),
                "prefix": plaintext[:11],
                "scope": json.dumps(["*"]),
                "created_at": now,
            },
        )

    # Step 2: drop users.api_key via Alembic batch_alter_table (handles SQLite FK refs).
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("api_key")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    col_names = {c["name"] for c in inspector.get_columns("users")}
    if "api_key" in col_names:
        return  # already present

    # Re-add the column as nullable (plaintext cannot be recovered — design intent).
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("api_key", sa.Text(), nullable=True))
