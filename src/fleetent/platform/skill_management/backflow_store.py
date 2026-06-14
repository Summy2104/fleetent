"""Persistence layer for agent skill backflow proposals.

Backflow = a drifted agent home skill copy nominated for governance review,
potentially to be accepted back into the shared pool (accept), discarded
(reject), or promoted as a new named skill (fork).

The ``backflow_proposals`` table lives in the management DB (Alembic-managed);
it is never touched by agent runtime modules.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def nominate(
    *,
    agent_id: int,
    skill_name: str,
    proposed_content: str,
    pool_dir: Path,
) -> int:
    """Create a pending backflow proposal for a drifted agent skill copy.

    Args:
        agent_id: The agent whose home copy is being nominated.
        skill_name: The skill to nominate for backflow.
        proposed_content: The SKILL.md content of the evolved home copy.
        pool_dir: The shared pool directory (used to detect conflict at nomination time).

    Returns:
        The new proposal row id.

    Raises:
        ValueError: If the skill is not currently marked drifted for the agent.
    """
    from fleetent.platform.skill_management import skill_admin_store

    drift_state = skill_admin_store.get_drift(agent_id, skill_name)
    if not drift_state.get("drift"):
        raise ValueError(
            f"skill {skill_name!r} is not drifted for agent {agent_id}; cannot nominate backflow"
        )

    base_version: str | None = drift_state.get("base_version")

    # Detect conflict: pool content has moved since the last materialization.
    conflict = _detect_conflict(pool_dir, skill_name, base_version)

    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO backflow_proposals
                (status, agent_id, skill_name, base_version, proposed_content,
                 conflict, overridden_head, forked_as, created_at, updated_at)
            VALUES
                ('pending', :agent_id, :skill_name, :base_version, :proposed_content,
                 :conflict, NULL, NULL, :created_at, :updated_at)
            """,
            {
                "agent_id": agent_id,
                "skill_name": skill_name,
                "base_version": base_version,
                "proposed_content": proposed_content,
                "conflict": 1 if conflict else 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
    assert row is not None
    return int(row["id"])


def _detect_conflict(pool_dir: Path, skill_name: str, base_version: str | None) -> bool:
    """Return True if the pool skill has changed since base_version was captured."""
    if base_version is None:
        return False
    skill_dir = pool_dir / skill_name
    if not skill_dir.exists():
        return False
    from hashlib import sha256

    digest = sha256()
    for path in sorted(p for p in skill_dir.rglob("*") if p.is_file() and ".git" not in p.parts):
        digest.update(path.relative_to(skill_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    current_hash = digest.hexdigest()
    return current_hash != base_version


def get_proposal(proposal_id: int) -> dict[str, Any] | None:
    """Return the proposal row by id, or None if not found."""
    row = (
        _database()
        .execute(
            """
            SELECT id, status, agent_id, skill_name, base_version, proposed_content,
                   conflict, overridden_head, forked_as, created_at, updated_at
            FROM backflow_proposals
            WHERE id = :proposal_id
            """,
            {"proposal_id": proposal_id},
        )
        .fetchone()
    )
    return dict(row) if row is not None else None


def list_proposals(
    *,
    skill_name: str | None = None,
    status: str | None = "pending",
    agent_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return backflow proposals matching the given filters."""
    conditions = []
    params: dict[str, Any] = {}
    if skill_name is not None:
        conditions.append("skill_name = :skill_name")
        params["skill_name"] = skill_name
    if status is not None:
        conditions.append("status = :status")
        params["status"] = status
    if agent_id is not None:
        conditions.append("agent_id = :agent_id")
        params["agent_id"] = agent_id
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = (
        _database()
        .execute(
            f"""
            SELECT id, status, agent_id, skill_name, base_version, proposed_content,
                   conflict, overridden_head, forked_as, created_at, updated_at
            FROM backflow_proposals
            {where}
            ORDER BY created_at DESC
            """,
            params,
        )
        .fetchall()
    )
    return [dict(r) for r in rows]


def get_proposal_diff(proposal_id: int, *, pool_dir: Path) -> dict[str, Any]:
    """Return unified diffs for a backflow proposal.

    Returns a dict with:
    - ``diff_vs_base``: evolved copy vs what was materialized (base_version content)
    - ``diff_vs_head``: evolved copy vs current pool head content
    - ``conflict``: True if pool has advanced past base_version
    """
    import difflib

    row = get_proposal(proposal_id)
    if row is None:
        raise ValueError(f"proposal {proposal_id} not found")

    proposed = row["proposed_content"]
    skill_name = row["skill_name"]
    base_version: str | None = row["base_version"]

    # Current pool head content
    pool_skill_dir = pool_dir / skill_name
    head_content: str | None = None
    if pool_skill_dir.exists():
        skill_md = pool_skill_dir / "SKILL.md"
        if skill_md.is_file():
            head_content = skill_md.read_text(encoding="utf-8")

    # base content: reconstruct from pool git at base_version commit
    base_content: str | None = None
    if base_version is not None:
        from fleetent.platform.skill_management.pool_git import pool_content_at

        base_content = pool_content_at(pool_dir, skill_name, base_version)

    # Conflict: pool head differs from what was materialized
    conflict = _detect_conflict(pool_dir, skill_name, base_version)

    def _diff(a: str | None, b: str | None, fromfile: str, tofile: str) -> str:
        if a is None and b is None:
            return ""
        lines_a = (a or "").splitlines(keepends=True)
        lines_b = (b or "").splitlines(keepends=True)
        return "".join(difflib.unified_diff(lines_a, lines_b, fromfile=fromfile, tofile=tofile))

    return {
        "diff_vs_base": _diff(base_content, proposed, "base", "evolved"),
        "diff_vs_head": _diff(head_content, proposed, "head", "evolved"),
        "conflict": conflict,
    }


def set_status(
    proposal_id: int,
    status: str,
    *,
    overridden_head: str | None = None,
    forked_as: str | None = None,
) -> None:
    """Update proposal status and optional metadata fields."""
    if status not in {"pending", "accepted", "rejected", "forked"}:
        raise ValueError(f"unknown status: {status!r}")
    with _database().transaction() as conn:
        conn.execute(
            """
            UPDATE backflow_proposals
            SET status = :status,
                overridden_head = COALESCE(:overridden_head, overridden_head),
                forked_as = COALESCE(:forked_as, forked_as),
                updated_at = :updated_at
            WHERE id = :proposal_id
            """,
            {
                "proposal_id": proposal_id,
                "status": status,
                "overridden_head": overridden_head,
                "forked_as": forked_as,
                "updated_at": _now(),
            },
        )
