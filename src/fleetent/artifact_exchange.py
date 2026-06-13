"""Unified file-exchange ledger, namespace resolution, attribution and views.

The `/exchange/<server_id>/<rel>` namespace is the second logical root (besides
`/workspace`) the file fence understands. This module is the agent-side governance
core behind it: an `artifacts` ledger (provenance + ownership metadata — never a
model interface), effective-root resolution for MCP servers, attribution access
control (a session may only reach its own artifacts), and the per-session hard-link
view that is read-only mounted into the sandbox as `/exchange`.

Injection mirrors `schedule_store` (`set_state_db` at agent boot); SQL uses named
parameters through the unified DB boundary. No `fleetent.platform.*` import.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fleetent.db import SQLiteDatabase

if TYPE_CHECKING:
    from fleetent.integrations.mcp.client import McpServerConfig

# The logical second root the file fence understands (besides /workspace).
EXCHANGE_ROOT = "/exchange"

# server_id → effective host file root, populated at MCP server registration.
_server_roots: dict[str, Path] = {}

_state_db: SQLiteDatabase | None = None


class ExchangeResolutionError(ValueError):
    """A /exchange path could not be resolved: malformed, escaping, unregistered,
    cross-session without approval, or the underlying artifact no longer exists."""


def set_state_db(db: SQLiteDatabase) -> None:
    """Inject the per-agent state DB.  Called once at agent boot via agent_app."""
    global _state_db
    _state_db = db


def _database() -> SQLiteDatabase:
    if _state_db is None:
        raise RuntimeError(
            "artifact_exchange: state_db not initialized — call set_state_db(db) at boot"
        )
    return _state_db


@dataclass(frozen=True)
class Artifact:
    """One ledger row: a file produced by an MCP server under /exchange."""

    artifact_id: str
    server_id: str
    rel_path: str
    session_id: str | None
    user_id: str | None
    filename: str | None
    mime: str | None
    size: int | None
    created_at: str | None


def register(
    *,
    server_id: str,
    rel_path: str,
    session_id: str | None,
    user_id: str | None = None,
    filename: str | None = None,
    mime: str | None = None,
    size: int | None = None,
) -> str:
    """Record (or refresh) an artifact and return its id.

    Idempotent on ``(server_id, rel_path, session_id)``: re-registering the same file
    (the chokepoint rewrite and the diff fallback may both see it) refreshes mutable
    metadata and returns the existing id rather than inserting a duplicate.
    """
    existing = (
        _database()
        .execute(
            "SELECT artifact_id FROM artifacts "
            "WHERE server_id = :server_id AND rel_path = :rel_path "
            "AND session_id IS :session_id",
            {"server_id": server_id, "rel_path": rel_path, "session_id": session_id},
        )
        .fetchone()
    )
    if existing is not None:
        artifact_id = existing["artifact_id"]
        _database().execute(
            "UPDATE artifacts SET user_id = :user_id, filename = :filename, "
            "mime = :mime, size = :size WHERE artifact_id = :artifact_id",
            {
                "artifact_id": artifact_id,
                "user_id": user_id,
                "filename": filename,
                "mime": mime,
                "size": size,
            },
        )
        return str(artifact_id)

    artifact_id = str(uuid.uuid4())
    _database().execute(
        "INSERT INTO artifacts ("
        "artifact_id, server_id, rel_path, session_id, user_id, filename, mime, size, created_at"
        ") VALUES ("
        ":artifact_id, :server_id, :rel_path, :session_id, :user_id, :filename, :mime, :size,"
        " :created_at)",
        {
            "artifact_id": artifact_id,
            "server_id": server_id,
            "rel_path": rel_path,
            "session_id": session_id,
            "user_id": user_id,
            "filename": filename,
            "mime": mime,
            "size": size,
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    return artifact_id


def get(artifact_id: str) -> Artifact | None:
    """Return the ledger row for an id, or None."""
    row = (
        _database()
        .execute(
            "SELECT * FROM artifacts WHERE artifact_id = :artifact_id",
            {"artifact_id": artifact_id},
        )
        .fetchone()
    )
    return _row_to_artifact(row) if row is not None else None


def list_by_session(session_id: str) -> list[Artifact]:
    """Return all artifacts owned by a session, newest first."""
    rows = (
        _database()
        .execute(
            "SELECT * FROM artifacts WHERE session_id = :session_id ORDER BY created_at DESC",
            {"session_id": session_id},
        )
        .fetchall()
    )
    return [_row_to_artifact(row) for row in rows]


def _find_by_path(server_id: str, rel_path: str) -> Artifact | None:
    """Return the artifact registered at (server_id, rel_path), or None."""
    row = (
        _database()
        .execute(
            "SELECT * FROM artifacts WHERE server_id = :server_id AND rel_path = :rel_path "
            "ORDER BY created_at DESC LIMIT 1",
            {"server_id": server_id, "rel_path": rel_path},
        )
        .fetchone()
    )
    return _row_to_artifact(row) if row is not None else None


def _row_to_artifact(row: dict[str, Any]) -> Artifact:
    return Artifact(
        artifact_id=row["artifact_id"],
        server_id=row["server_id"],
        rel_path=row["rel_path"],
        session_id=row["session_id"],
        user_id=row["user_id"],
        filename=row["filename"],
        mime=row["mime"],
        size=row["size"],
        created_at=row["created_at"],
    )


# ── effective root + namespace resolution ──────────────────────────────────────


def effective_root(server: McpServerConfig, agent_home: Path) -> Path:
    """Resolve a server's effective file root (what `/exchange/<id>` maps to).

    Precedence (D1): explicit ``file_root`` > explicit ``XDG_DATA_HOME`` env (adopt an
    existing config in place, zero migration) > the convention
    ``<agent_home>/exchange/<server_id>/data``.
    """
    if server.file_root:
        return Path(server.file_root)
    xdg = server.env.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    return agent_home / "exchange" / server.id / "data"


def register_server_root(server_id: str, root: Path) -> None:
    """Bind a server's effective file root so `/exchange/<server_id>` can resolve."""
    _server_roots[server_id] = root


def resolve(path: str, session_id: str | None, *, approved: bool = False) -> Path:
    """Resolve a ``/exchange/<server_id>/<rel>`` path to a host file with attribution.

    Enforces (D4): the path is well-formed and inside the server's registered root (no
    ``..`` escape), the artifact is in the ledger, and — unless ``approved`` — it is
    owned by ``session_id``. Raises `ExchangeResolutionError` for any violation, or when
    the underlying file no longer exists.
    """
    server_id, rel = _split_exchange_path(path)
    root = _server_roots.get(server_id)
    if root is None:
        raise ExchangeResolutionError(f"server not registered for exchange: {server_id!r}")

    base = os.path.normpath(str(root))
    candidate = os.path.normpath(os.path.join(base, rel))
    if candidate != base and not candidate.startswith(base + os.sep):
        raise ExchangeResolutionError(f"path escapes exchange root: {path!r}")

    artifact = _find_by_path(server_id, rel)
    if artifact is None:
        raise ExchangeResolutionError(f"no registered artifact for {path!r}")
    if not approved and artifact.session_id != session_id:
        raise ExchangeResolutionError(
            f"artifact {path!r} belongs to another session; use send_im_message (approval)"
        )
    if not Path(candidate).is_file():
        raise ExchangeResolutionError(f"工件已不存在（file gone）: {path!r}")
    return Path(candidate)


def _split_exchange_path(path: str) -> tuple[str, str]:
    norm = path if path.startswith("/") else "/" + path
    prefix = EXCHANGE_ROOT + "/"
    if not norm.startswith(prefix):
        raise ExchangeResolutionError(f"not an /exchange path: {path!r}")
    remainder = norm[len(prefix) :]
    server_id, sep, rel = remainder.partition("/")
    if not server_id or not sep or not rel:
        raise ExchangeResolutionError(f"malformed /exchange path: {path!r}")
    return server_id, rel
