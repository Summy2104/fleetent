"""Unified file-exchange ledger, namespace resolution, attribution and views.

The `/exchange/<server_id>/<rel>` namespace is the second logical root (besides
`/workspace`) the file fence understands. This module is the agent-side governance
core behind it: an `artifacts` ledger (provenance + ownership metadata — never a
model interface), effective-root resolution for MCP servers, attribution access
control (a run may only reach artifacts owned by its workspace scope, D0), and the
per-scope hard-link view that is read-only mounted into the sandbox as `/exchange`.

Injection mirrors `schedule_store` (`set_state_db` at agent boot); SQL uses named
parameters through the unified DB boundary. No `fleetent.platform.*` import.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fleetent.db import SQLiteDatabase
from fleetent.structured_logging import get_logger

if TYPE_CHECKING:
    from fleetent.integrations.mcp.client import McpServerConfig

_logger = get_logger("artifact_exchange")

# The logical second root the file fence understands (besides /workspace).
EXCHANGE_ROOT = "/exchange"

# server_id → effective host file root, populated at MCP server registration.
_server_roots: dict[str, Path] = {}

_state_db: SQLiteDatabase | None = None

# Root of the per-scope hard-link views (`<agent_home>/exchange/.views/`), set at boot.
# Each artifact is linked to `<_views_root>/<scope_key>/<server_id>/<rel>` so the sandbox
# can ro-mount exactly one scope's view. None = views disabled (no linking).
_views_root: Path | None = None
# Servers whose effective root is on a different filesystem than the views root, so a
# hard link is impossible (EXDEV) — their consumption must fall back to staging copy (D5).
_staging_degraded_servers: set[str] = set()


def set_views_root(path: Path) -> None:
    """Set the per-scope hard-link views root.  Called once at agent boot via agent_app."""
    global _views_root
    _views_root = path


def view_dir(scope_key: str | None) -> Path | None:
    """The (created) scope view directory to ro-mount at /exchange, or None if disabled.

    Ensured to exist (possibly empty) before a container is created so the bind mount has
    a source and later-linked artifacts appear live (D5: container first, files after)."""
    if _views_root is None or not scope_key:
        return None
    d = _views_root / scope_key
    d.mkdir(parents=True, exist_ok=True)
    return d


def _link_into_view(server_id: str, rel_path: str, scope_key: str | None) -> None:
    """Best-effort hard-link an artifact into its scope view (§4.1/4.2).

    Links `<server_root>/<rel>` → `<_views_root>/<scope_key>/<server_id>/<rel>`. Refreshes
    a stale link (source inode changed). A cross-filesystem failure (EXDEV) flags the
    server for staging degrade (D5) and logs — never raises (registration must not fail).
    """
    if _views_root is None or not scope_key:
        return
    root = _server_roots.get(server_id)
    if root is None:
        return
    src = Path(root) / rel_path
    if not src.is_file():
        return
    link = _views_root / scope_key / server_id / rel_path
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.exists() and link.stat().st_ino != src.stat().st_ino:
            link.unlink()  # stale link → source replaced (new inode); refresh
        if not link.exists():
            os.link(src, link)
    except OSError as exc:
        _staging_degraded_servers.add(server_id)
        _logger.warn("artifact_view_link_failed", server_id=server_id, rel=rel_path, error=str(exc))


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
    """One ledger row: a file produced by an MCP server under /exchange.

    `scope_key` is the visibility/ownership key (D0): the run's workspace scope key
    (session_id when workspace_scope is `session`, agent_name when `agent`; same
    source as the /workspace mount). `session_id`/`user_id` record the concrete
    producing call for AUDIT only — they do not drive access control.
    """

    artifact_id: str
    server_id: str
    rel_path: str
    scope_key: str | None
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
    scope_key: str | None,
    session_id: str | None = None,
    user_id: str | None = None,
    filename: str | None = None,
    mime: str | None = None,
    size: int | None = None,
) -> str:
    """Record (or refresh) an artifact and return its id.

    Idempotent on ``(server_id, rel_path, scope_key)`` (D0): re-registering the same
    file under the same scope (the chokepoint rewrite and the diff fallback may both
    see it) refreshes mutable + audit metadata and returns the existing id rather than
    inserting a duplicate. The same path under a *different* scope is a distinct row.
    """
    existing = (
        _database()
        .execute(
            "SELECT artifact_id FROM artifacts "
            "WHERE server_id = :server_id AND rel_path = :rel_path "
            "AND scope_key IS :scope_key",
            {"server_id": server_id, "rel_path": rel_path, "scope_key": scope_key},
        )
        .fetchone()
    )
    if existing is not None:
        artifact_id = existing["artifact_id"]
        _database().execute(
            "UPDATE artifacts SET session_id = :session_id, user_id = :user_id, "
            "filename = :filename, mime = :mime, size = :size WHERE artifact_id = :artifact_id",
            {
                "artifact_id": artifact_id,
                "session_id": session_id,
                "user_id": user_id,
                "filename": filename,
                "mime": mime,
                "size": size,
            },
        )
        _link_into_view(server_id, rel_path, scope_key)
        return str(artifact_id)

    artifact_id = str(uuid.uuid4())
    _database().execute(
        "INSERT INTO artifacts ("
        "artifact_id, server_id, rel_path, scope_key, session_id, user_id, filename, mime, size,"
        " created_at"
        ") VALUES ("
        ":artifact_id, :server_id, :rel_path, :scope_key, :session_id, :user_id, :filename, :mime,"
        " :size, :created_at)",
        {
            "artifact_id": artifact_id,
            "server_id": server_id,
            "rel_path": rel_path,
            "scope_key": scope_key,
            "session_id": session_id,
            "user_id": user_id,
            "filename": filename,
            "mime": mime,
            "size": size,
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    _link_into_view(server_id, rel_path, scope_key)
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


def list_by_scope(scope_key: str) -> list[Artifact]:
    """Return all artifacts owned by a workspace scope (D0), newest first.

    Drives the per-scope hard-link view (`.views/<scope_key>/`) and scope-level audit.
    """
    rows = (
        _database()
        .execute(
            "SELECT * FROM artifacts WHERE scope_key = :scope_key ORDER BY created_at DESC",
            {"scope_key": scope_key},
        )
        .fetchall()
    )
    return [_row_to_artifact(row) for row in rows]


def _find_by_path(server_id: str, rel_path: str, scope_key: str | None) -> Artifact | None:
    """Return the artifact registered at (server_id, rel_path) for THIS scope, or None.

    Scope-filtered (D4): never 'newest at path across scopes' — a same-path artifact
    owned by another scope must not be returned here (it would either leak or, after the
    ownership check, falsely deny the requester's own file).
    """
    row = (
        _database()
        .execute(
            "SELECT * FROM artifacts WHERE server_id = :server_id AND rel_path = :rel_path "
            "AND scope_key IS :scope_key ORDER BY created_at DESC LIMIT 1",
            {"server_id": server_id, "rel_path": rel_path, "scope_key": scope_key},
        )
        .fetchone()
    )
    return _row_to_artifact(row) if row is not None else None


def _find_any_by_path(server_id: str, rel_path: str) -> Artifact | None:
    """Return the newest artifact at (server_id, rel_path) regardless of scope.

    Used only on the approved (post-permission-gate) cross-scope path and to
    distinguish 'cross-scope, needs approval' from 'never registered' in `resolve`.
    """
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
        scope_key=row["scope_key"],
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


def server_root(server_id: str) -> Path | None:
    """The registered effective file root for a server, or None if unbound."""
    return _server_roots.get(server_id)


# Path tail after the effective root: stop at whitespace and common JSON/text delimiters
# so a host path embedded in result text (`"localPath": "<root>/a/b.xlsx"`) is captured
# without swallowing the trailing quote/comma.
_PATH_TAIL = r'(/[^\s"\'<>),;]+)'


def _safe_size(path: str) -> int | None:
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def snapshot_products(root: Path | str) -> dict[str, tuple[float, int]]:
    """Map ``rel_path -> (mtime, size)`` for files under ``root`` (call-window diff input).

    Skips dotfiles (any dot-prefixed path segment) and ``*.tmp`` so a server's settings/
    cache/scratch writes never enter the ledger. Returns ``{}`` for a missing root.
    """
    base = Path(root)
    snap: dict[str, tuple[float, int]] = {}
    if not base.is_dir():
        return snap
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(base)
        if any(part.startswith(".") for part in rel.parts) or p.suffix == ".tmp":
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        snap[str(rel)] = (st.st_mtime, st.st_size)
    return snap


def diff_register(
    server_id: str,
    root: Path | str,
    before: dict[str, tuple[float, int]],
    scope_key: str | None,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
) -> list[str]:
    """Register product-dir files new/changed since ``before`` — the call-window diff (D2).

    The fallback for products the deterministic rewrite missed (result text never named
    the path). A no-op without a ``scope_key`` (cannot attribute). Returns the rel_paths
    registered. ``register`` is idempotent on ``(server, rel, scope_key)`` so files the
    rewrite already registered are harmlessly refreshed, not duplicated.
    """
    if not scope_key:
        return []
    after = snapshot_products(root)
    newly = [rel for rel, meta in after.items() if before.get(rel) != meta]
    for rel in newly:
        register(
            server_id=server_id,
            rel_path=rel,
            scope_key=scope_key,
            session_id=session_id,
            user_id=user_id,
            filename=os.path.basename(rel),
            size=after[rel][1],
        )
    return newly


def rewrite_and_register(
    server_id: str,
    text: str,
    scope_key: str | None,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
) -> str:
    """Rewrite in-root host paths in a tool result to `/exchange/<server_id>/<rel>` + register.

    The deterministic discovery layer (D2): a host absolute path inside the server's
    registered effective root is prefix-replaced with its `/exchange` canonical form and
    the file registered in the ledger, attributed to the current run's ``scope_key``
    (``session_id``/``user_id`` recorded for audit only). A no-op when the server has no
    registered root or no ``scope_key`` is available (cannot attribute) — text byte-identical.
    Paths outside the root are never touched.
    """
    root = _server_roots.get(server_id)
    if root is None or not scope_key:
        return text
    base = os.path.normpath(str(root))
    pattern = re.compile(re.escape(base) + _PATH_TAIL)
    rewritten: dict[str, str] = {}

    def _sub(match: re.Match[str]) -> str:
        rel = match.group(1).lstrip("/")
        if rel not in rewritten:
            register(
                server_id=server_id,
                rel_path=rel,
                scope_key=scope_key,
                session_id=session_id,
                user_id=user_id,
                filename=os.path.basename(rel),
                size=_safe_size(os.path.join(base, rel)),
            )
            rewritten[rel] = f"{EXCHANGE_ROOT}/{server_id}/{rel}"
        return rewritten[rel]

    return pattern.sub(_sub, text)


def resolve(path: str, scope_key: str | None, *, approved: bool = False) -> Path:
    """Resolve a ``/exchange/<server_id>/<rel>`` path to a host file with attribution.

    Enforces (D4): the path is well-formed and inside the server's registered root (no
    ``..`` escape), and the artifact is owned by THIS workspace scope (`scope_key`).
    The only cross-scope exemption is ``approved`` (the call already passed the
    permission gate — send_file upgrade / send_im_message files). Raises
    `ExchangeResolutionError` for any violation, or when the underlying file is gone.
    """
    server_id, rel = _split_exchange_path(path)
    root = _server_roots.get(server_id)
    if root is None:
        raise ExchangeResolutionError(f"server not registered for exchange: {server_id!r}")

    base = os.path.normpath(str(root))
    candidate = os.path.normpath(os.path.join(base, rel))
    if candidate != base and not candidate.startswith(base + os.sep):
        raise ExchangeResolutionError(f"path escapes exchange root: {path!r}")

    # Scope-filtered lookup first: my own row wins over any same-path other-scope row.
    artifact = _find_by_path(server_id, rel, scope_key)
    if artifact is None:
        # Not mine. Either it belongs to another scope (cross-scope) or was never
        # registered — distinguished by a scope-agnostic lookup. Cross-scope is only
        # reachable when the call already passed the permission gate (`approved`).
        other = _find_any_by_path(server_id, rel)
        if other is None:
            raise ExchangeResolutionError(f"no registered artifact for {path!r}")
        if not approved:
            raise ExchangeResolutionError(
                f"artifact {path!r} 属于另一 scope（belongs to another scope）；"
                "use send_im_message (approval)"
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
