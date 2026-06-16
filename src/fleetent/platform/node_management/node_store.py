"""Management-plane persistence for registered agent nodes."""

from __future__ import annotations

import datetime
import json
import secrets
import sqlite3
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.user_store import _hash_key

_COLS = "id, name, key_hash, labels, registered_at, last_seen_at, created_at, updated_at"


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def register_node(
    node_id: str,
    *,
    name: str | None = None,
    labels: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    plaintext = f"ma-{secrets.token_hex(32)}"
    now = _now()
    encoded_labels = json.dumps(labels or {})
    try:
        with _database().transaction() as conn:
            conn.execute(
                """
                INSERT INTO nodes
                    (
                        id,
                        name,
                        key_hash,
                        labels,
                        registered_at,
                        last_seen_at,
                        created_at,
                        updated_at
                    )
                VALUES
                    (
                        :id,
                        :name,
                        :key_hash,
                        :labels,
                        :registered_at,
                        NULL,
                        :created_at,
                        :updated_at
                    )
                """,
                {
                    "id": node_id,
                    "name": name,
                    "key_hash": _hash_key(plaintext),
                    "labels": encoded_labels,
                    "registered_at": now,
                    "created_at": now,
                    "updated_at": now,
                },
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"node {node_id!r} already exists") from exc
    node = get_node(node_id)
    assert node is not None
    return plaintext, node


def get_node(node_id: str) -> dict[str, Any] | None:
    row = (
        _database().execute(f"SELECT {_COLS} FROM nodes WHERE id = :id", {"id": node_id}).fetchone()
    )
    return _decode(row) if row else None


def list_nodes() -> list[dict[str, Any]]:
    rows = _database().execute(f"SELECT {_COLS} FROM nodes ORDER BY id").fetchall()
    return [_decode(row) for row in rows]


def resolve_node_key(plaintext: str) -> dict[str, Any] | None:
    row = (
        _database()
        .execute(
            f"SELECT {_COLS} FROM nodes WHERE key_hash = :key_hash",
            {"key_hash": _hash_key(plaintext)},
        )
        .fetchone()
    )
    return _decode(row) if row else None


def deregister_node(node_id: str) -> None:
    placement_count = (
        _database()
        .execute(
            "SELECT COUNT(*) AS count FROM agent_placements WHERE node_id = :node_id",
            {"node_id": node_id},
        )
        .fetchone()
    )
    assert placement_count is not None
    if int(placement_count["count"]) > 0:
        raise ValueError(f"node {node_id!r} still has pinned agents")
    _database().execute("DELETE FROM nodes WHERE id = :id", {"id": node_id})


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["labels"] = json.loads(out["labels"]) if out.get("labels") else {}
    return out
