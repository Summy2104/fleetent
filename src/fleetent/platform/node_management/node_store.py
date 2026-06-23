"""Management-plane persistence for registered agent nodes."""

from __future__ import annotations

import datetime
import json
import logging
import secrets
import sqlite3
from contextlib import suppress
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.platform.agent_lifecycle import secret_store
from fleetent.user_store import _hash_key

_COLS = "id, name, key_hash, labels, registered_at, last_seen_at, created_at, updated_at"
_STATUS_COLS = "agent_id, node_id, phase, pid, health, detail, reported_at"
_NODE_KEY_CACHE: dict[str, str] = {}
_logger = logging.getLogger(__name__)


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
    _NODE_KEY_CACHE[node_id] = plaintext
    try:
        secret_store.set(None, _node_service_key_env(node_id), plaintext, "node.register")
    except Exception as exc:
        _logger.error(
            "Failed to persist service key for node %r — check FLEETENT_SECRET_KEY or secret "
            "backend: %s",
            node_id,
            exc,
        )
        _NODE_KEY_CACHE.pop(node_id, None)
        with suppress(Exception):
            _database().execute("DELETE FROM nodes WHERE id = :id", {"id": node_id})
        raise
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


def get_node_service_key(node_id: str) -> str | None:
    cached = _NODE_KEY_CACHE.get(node_id)
    if cached:
        return cached
    try:
        return secret_store.get_decrypted(None, _node_service_key_env(node_id))
    except Exception:
        return None


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
    _NODE_KEY_CACHE.pop(node_id, None)
    with suppress(Exception):
        secret_store.delete(None, _node_service_key_env(node_id))


def touch_last_seen(node_id: str) -> None:
    now = _now()
    _database().execute(
        """
        UPDATE nodes
        SET last_seen_at = :last_seen_at, updated_at = :updated_at
        WHERE id = :id
        """,
        {"id": node_id, "last_seen_at": now, "updated_at": now},
    )


def upsert_agent_status(
    agent_id: int,
    *,
    node_id: str,
    phase: str,
    pid: int | None = None,
    health: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    reported_at = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO node_agent_status (
                agent_id, node_id, phase, pid, health, detail, reported_at
            )
            VALUES (:agent_id, :node_id, :phase, :pid, :health, :detail, :reported_at)
            ON CONFLICT(agent_id) DO UPDATE SET
                node_id = excluded.node_id,
                phase = excluded.phase,
                pid = excluded.pid,
                health = excluded.health,
                detail = excluded.detail,
                reported_at = excluded.reported_at
            """,
            {
                "agent_id": agent_id,
                "node_id": node_id,
                "phase": phase,
                "pid": pid,
                "health": health,
                "detail": detail,
                "reported_at": reported_at,
            },
        )
    row = (
        _database()
        .execute(
            f"SELECT {_STATUS_COLS} FROM node_agent_status WHERE agent_id = :agent_id",
            {"agent_id": agent_id},
        )
        .fetchone()
    )
    assert row is not None
    return dict(row)


def get_agent_status(agent_id: int) -> dict[str, Any] | None:
    """Read the last reported actual state for one agent (read-only projection)."""
    row = (
        _database()
        .execute(
            f"SELECT {_STATUS_COLS} FROM node_agent_status WHERE agent_id = :agent_id",
            {"agent_id": agent_id},
        )
        .fetchone()
    )
    return dict(row) if row else None


def list_agent_status() -> list[dict[str, Any]]:
    """Read every agent's last reported actual state (read-only projection)."""
    rows = (
        _database()
        .execute(f"SELECT {_STATUS_COLS} FROM node_agent_status ORDER BY agent_id")
        .fetchall()
    )
    return [dict(row) for row in rows]


def list_agent_status_by_node(node_id: str) -> list[dict[str, Any]]:
    rows = (
        _database()
        .execute(
            (
                f"SELECT {_STATUS_COLS} FROM node_agent_status "
                "WHERE node_id = :node_id ORDER BY agent_id"
            ),
            {"node_id": node_id},
        )
        .fetchall()
    )
    return [dict(row) for row in rows]


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["labels"] = json.loads(out["labels"]) if out.get("labels") else {}
    return out


def _node_service_key_env(node_id: str) -> str:
    return f"FLEETENT_NODE_FORWARDER_KEY__{node_id}"
