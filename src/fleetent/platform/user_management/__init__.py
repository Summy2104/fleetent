"""User-management package public helpers."""

import datetime

from fleetent import user_store
from fleetent.platform.user_management import api_key_store


def migrate_api_keys() -> list[str]:
    """Move legacy ``users.api_key`` values into ``api_keys``. Idempotent."""
    db = user_store._db()
    moved: list[str] = []
    existing = {r["key_hash"] for r in db.execute("SELECT key_hash FROM api_keys").fetchall()}
    for user_id, plaintext_key in user_store.list_legacy_api_keys():
        key_hash = api_key_store._hash(plaintext_key)
        if key_hash in existing:
            continue
        with db.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO api_keys
                       (user_id, key_hash, prefix, scope, note, created_at, call_count)
                   VALUES (:user_id, :key_hash, :prefix, '["*"]', 'migrated', :created_at, 0)""",
                {
                    "user_id": user_id,
                    "key_hash": key_hash,
                    "prefix": plaintext_key[:11],
                    "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
                },
            )
        existing.add(key_hash)
        moved.append(user_id)
    return moved
