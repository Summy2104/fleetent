"""Persistence layer for agent skill backflow proposals.

Backflow = a drifted agent home skill copy nominated for governance review,
potentially to be accepted back into the shared pool (accept), discarded
(reject), or promoted as a new named skill (fork).

The ``backflow_proposals`` table lives in the management DB (Alembic-managed);
it is never touched by agent runtime modules.
"""

from __future__ import annotations

import datetime
import io
import json
import tarfile
from pathlib import Path
from typing import Any

import httpx

from fleetent import agent_store, paths
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
    proposed_content: str | None = None,
    pool_dir: Path,
) -> int:
    """Create a pending backflow proposal for a drifted agent skill copy.

    Args:
        agent_id: The agent whose home copy is being nominated.
        skill_name: The skill to nominate for backflow.
        proposed_content: Optional legacy fallback for SKILL.md-only nominations.
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
    base_commit: str | None = drift_state.get("base_commit")
    proposed_bundle = _capture_proposed_bundle(
        agent_id=agent_id,
        skill_name=skill_name,
        proposed_content=proposed_content,
    )

    # Detect conflict: pool content has moved since the last materialization.
    conflict = _detect_conflict(pool_dir, skill_name, base_version)

    now = _now()
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO backflow_proposals
                (status, agent_id, skill_name, base_version, base_commit, proposed_bundle,
                 conflict, overridden_head, forked_as, created_at, updated_at)
            VALUES
                ('pending', :agent_id, :skill_name, :base_version, :base_commit, :proposed_bundle,
                 :conflict, NULL, NULL, :created_at, :updated_at)
            """,
            {
                "agent_id": agent_id,
                "skill_name": skill_name,
                "base_version": base_version,
                "base_commit": base_commit,
                "proposed_bundle": json.dumps(proposed_bundle, sort_keys=True),
                "conflict": 1 if conflict else 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
    assert row is not None
    return int(row["id"])


def nominate_if_absent(*, agent_id: int, skill_name: str, pool_dir: Path) -> int | None:
    """Nominate a drifted skill for backflow unless a pending proposal already exists.

    Dedup is checked first so the (potentially remote) bundle capture in ``nominate``
    is skipped when a pending proposal is already on file.

    Args:
        agent_id: The agent whose drifted home copy is being nominated.
        skill_name: The skill to nominate for backflow.
        pool_dir: The shared pool directory (used to detect conflict at nomination time).

    Returns:
        The new proposal row id, or None if a pending proposal already exists.
    """
    existing = list_proposals(agent_id=agent_id, skill_name=skill_name, status="pending")
    if existing:
        return None
    return nominate(agent_id=agent_id, skill_name=skill_name, pool_dir=pool_dir)


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
            SELECT id, status, agent_id, skill_name, base_version, base_commit, proposed_bundle,
                   conflict, overridden_head, forked_as, created_at, updated_at
            FROM backflow_proposals
            WHERE id = :proposal_id
            """,
            {"proposal_id": proposal_id},
        )
        .fetchone()
    )
    return _row_to_proposal(row)


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
            SELECT id, status, agent_id, skill_name, base_version, base_commit, proposed_bundle,
                   conflict, overridden_head, forked_as, created_at, updated_at
            FROM backflow_proposals
            {where}
            ORDER BY created_at DESC
            """,
            params,
        )
        .fetchall()
    )
    proposals: list[dict[str, Any]] = []
    for row in rows:
        proposal = _row_to_proposal(row)
        if proposal is not None:
            proposals.append(proposal)
    return proposals


def _row_to_proposal(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    proposal = dict(row)
    proposal["proposed_bundle"] = json.loads(proposal["proposed_bundle"])
    return proposal


def _capture_proposed_bundle(
    *, agent_id: int, skill_name: str, proposed_content: str | None
) -> dict[str, str]:
    remote_bundle = _capture_bundle_from_owning_node(agent_id=agent_id, skill_name=skill_name)
    if remote_bundle is not None:
        return remote_bundle
    agent = agent_store.get_by_id(agent_id)
    if agent is not None:
        skill_dir = paths.tenant_agent_home_dir(agent.tenant_id, agent.name) / "skills" / skill_name
        if skill_dir.is_dir():
            bundle: dict[str, str] = {}
            for path in sorted(
                p for p in skill_dir.rglob("*") if p.is_file() and ".git" not in p.parts
            ):
                bundle[path.relative_to(skill_dir).as_posix()] = path.read_text(encoding="utf-8")
            if bundle:
                return bundle
    if proposed_content is None:
        raise ValueError(f"skill {skill_name!r} has no materialized bundle to nominate")
    return {"SKILL.md": proposed_content}


def _capture_bundle_from_owning_node(*, agent_id: int, skill_name: str) -> dict[str, str] | None:
    from fleetent.node.forwarder_contract import forwarder_base_url
    from fleetent.platform.node_management import node_store, placement_store

    agent = agent_store.get_by_id(agent_id)
    if agent is None:
        return None
    placement = placement_store.get_for_agent(agent_id)
    if placement is None:
        return None
    node_id = str(placement["node_id"])
    service_key = node_store.get_node_service_key(node_id)
    if not service_key:
        return None
    response = httpx.get(
        f"{forwarder_base_url(node_id)}/forward/agents/{agent.name}/skills/{skill_name}/bundle",
        headers={
            "Authorization": f"Bearer {service_key}",
            "X-Fleetent-Tenant-Id": agent.tenant_id,
        },
        timeout=10.0,
    )
    response.raise_for_status()
    bundle: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"unsafe node bundle member path: {member.name}")
            if any(part == ".git" for part in member_path.parts):
                raise ValueError(f"unsafe node bundle member path: {member.name}")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f"unable to extract node bundle member: {member.name}")
            relpath = Path(*member_path.parts[1:]).as_posix()
            bundle[relpath] = extracted.read().decode("utf-8")
    return bundle or None


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

    proposed_bundle: dict[str, str] = row["proposed_bundle"]
    skill_name = row["skill_name"]
    base_version: str | None = row["base_version"]
    base_commit: str | None = row["base_commit"]

    # Current pool head bundle
    pool_skill_dir = pool_dir / skill_name
    head_bundle: dict[str, str] | None = None
    if pool_skill_dir.exists():
        head_bundle = {}
        for path in sorted(
            p for p in pool_skill_dir.rglob("*") if p.is_file() and ".git" not in p.parts
        ):
            relpath = path.relative_to(pool_skill_dir).as_posix()
            head_bundle[relpath] = path.read_text(encoding="utf-8")

    # base bundle: reconstruct from pool git at base_commit
    base_bundle: dict[str, str] | None = None
    if base_commit is not None:
        from fleetent.platform.skill_management.pool_git import pool_bundle_at

        base_bundle = pool_bundle_at(pool_dir, skill_name, base_commit)

    # Conflict: pool head differs from what was materialized
    conflict = _detect_conflict(pool_dir, skill_name, base_version)

    def _bundle_diff(
        a: dict[str, str] | None, b: dict[str, str] | None, from_label: str, to_label: str
    ) -> str:
        if a is None and b is None:
            return ""
        left = a or {}
        right = b or {}
        parts: list[str] = []
        skill_md_left = left.get("SKILL.md")
        skill_md_right = right.get("SKILL.md")
        if skill_md_left is not None or skill_md_right is not None:
            parts.append(
                "".join(
                    difflib.unified_diff(
                        (skill_md_left or "").splitlines(keepends=True),
                        (skill_md_right or "").splitlines(keepends=True),
                        fromfile=f"{from_label}/SKILL.md",
                        tofile=f"{to_label}/SKILL.md",
                    )
                )
            )
        changed_paths: list[str] = []
        for relpath in sorted(set(left) | set(right)):
            if relpath == "SKILL.md":
                continue
            before = left.get(relpath)
            after = right.get(relpath)
            if before == after:
                continue
            if before is None:
                changed_paths.append(f"A {relpath}")
            elif after is None:
                changed_paths.append(f"D {relpath}")
            else:
                changed_paths.append(f"M {relpath}")
        if changed_paths:
            parts.append("Changed files:\n" + "\n".join(changed_paths) + "\n")
        return "".join(parts)

    if base_commit is None:
        diff_vs_base = "Base unknown; only diff_vs_head is available.\n"
    else:
        diff_vs_base = _bundle_diff(base_bundle, proposed_bundle, "base", "evolved")

    return {
        "diff_vs_base": diff_vs_base,
        "diff_vs_head": _bundle_diff(head_bundle, proposed_bundle, "head", "evolved"),
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
