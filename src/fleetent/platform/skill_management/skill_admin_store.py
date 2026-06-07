"""Management-face persistence for Skill administration.

Two concerns live here, both backed by the unified db runtime (named params, no ORM):

- ``agent_skills``: the Skill↔Agent enablement matrix used by the admin console.
  The engine (``skill`` domain) reads this as the per-agent desired-disabled state;
  this module only owns the management-side writes and reference-protection queries.
- ``skill_provenance``: the managed (spec-owned) / adhoc (DB-only) badge plus the
  ``drift`` flag and immutable-field set, used to coordinate with askit override flow.

Schema lifecycle is owned by Alembic (migration 010); this module never creates tables.
"""

import datetime
import json
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


# --- Skill ↔ Agent binding matrix ---------------------------------------------


def set_binding(agent_id: str, skill_name: str, enabled: bool, updated_by: str | None) -> None:
    """Upsert the enablement of ``skill_name`` for ``agent_id`` (idempotent)."""
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO agent_skills (agent_id, skill_name, enabled, updated_at, updated_by)
            VALUES (:agent_id, :skill_name, :enabled, :updated_at, :updated_by)
            ON CONFLICT(agent_id, skill_name) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            {
                "agent_id": agent_id,
                "skill_name": skill_name,
                "enabled": 1 if enabled else 0,
                "updated_at": _now(),
                "updated_by": updated_by,
            },
        )


def list_agents_for_skill(skill_name: str) -> list[dict[str, Any]]:
    """Return every agent binding for a skill, enabled or not."""
    return (
        _database()
        .execute(
            "SELECT agent_id, skill_name, enabled, updated_at, updated_by "
            "FROM agent_skills WHERE skill_name = :skill_name ORDER BY agent_id",
            {"skill_name": skill_name},
        )
        .fetchall()
    )


def list_skills_for_agent(agent_id: str) -> list[dict[str, Any]]:
    """Return every skill binding for an agent, enabled or not."""
    return (
        _database()
        .execute(
            "SELECT agent_id, skill_name, enabled, updated_at, updated_by "
            "FROM agent_skills WHERE agent_id = :agent_id ORDER BY skill_name",
            {"agent_id": agent_id},
        )
        .fetchall()
    )


def has_any_binding(agent_id: str) -> bool:
    """Whether the agent has at least one agent_skills row (enabled or not)."""
    row = (
        _database()
        .execute(
            "SELECT 1 FROM agent_skills WHERE agent_id = :agent_id LIMIT 1",
            {"agent_id": agent_id},
        )
        .fetchone()
    )
    return row is not None


def enabled_skill_names(agent_id: str) -> set[str]:
    """Skill names explicitly enabled (enabled=1) for the agent."""
    rows = (
        _database()
        .execute(
            "SELECT skill_name FROM agent_skills WHERE agent_id = :agent_id AND enabled = 1",
            {"agent_id": agent_id},
        )
        .fetchall()
    )
    return {str(r["skill_name"]) for r in rows}


def agents_enabling(skill_name: str) -> list[str]:
    """Return agent ids that explicitly enable the skill — drives delete protection."""
    rows = (
        _database()
        .execute(
            "SELECT agent_id FROM agent_skills "
            "WHERE skill_name = :skill_name AND enabled = 1 ORDER BY agent_id",
            {"skill_name": skill_name},
        )
        .fetchall()
    )
    return [r["agent_id"] for r in rows]


# --- Provenance (managed / adhoc) + drift -------------------------------------


def set_provenance(skill_name: str, source: str, immutable_fields: list[str] | None = None) -> None:
    """Record the managed/adhoc source (and optional immutable field set) for a skill."""
    if source not in {"managed", "adhoc"}:
        raise ValueError(f"unknown provenance source: {source}")
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO skill_provenance
                (skill_name, source, drift, immutable_fields, updated_at)
            VALUES (:skill_name, :source, 0, :immutable_fields, :updated_at)
            ON CONFLICT(skill_name) DO UPDATE SET
                source = excluded.source,
                immutable_fields = excluded.immutable_fields,
                updated_at = excluded.updated_at
            """,
            {
                "skill_name": skill_name,
                "source": source,
                "immutable_fields": json.dumps(immutable_fields) if immutable_fields else None,
                "updated_at": _now(),
            },
        )


def get_provenance(skill_name: str) -> dict[str, Any]:
    """Return provenance for a skill; skills with no row default to adhoc/no-drift."""
    row = (
        _database()
        .execute(
            "SELECT skill_name, source, drift, immutable_fields, last_deploy_at, updated_at "
            "FROM skill_provenance WHERE skill_name = :skill_name",
            {"skill_name": skill_name},
        )
        .fetchone()
    )
    if row is None:
        return {
            "skill_name": skill_name,
            "source": "adhoc",
            "drift": 0,
            "immutable_fields": None,
            "last_deploy_at": None,
            "updated_at": None,
        }
    return row


def mark_drift(skill_name: str) -> None:
    """Flag a managed skill as drifted because the UI changed it out-of-band."""
    _set_drift(skill_name, 1)


def clear_drift(skill_name: str) -> None:
    """Clear the drift flag (after promote/discard reconciles the skill)."""
    _set_drift(skill_name, 0)


def _set_drift(skill_name: str, value: int) -> None:
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO skill_provenance (skill_name, source, drift, updated_at)
            VALUES (:skill_name, 'adhoc', :drift, :updated_at)
            ON CONFLICT(skill_name) DO UPDATE SET
                drift = :drift,
                updated_at = :updated_at
            """,
            {"skill_name": skill_name, "drift": value, "updated_at": _now()},
        )


def is_immutable_change(skill_name: str, changed_fields: set[str]) -> bool:
    """True when a managed skill's edit touches any field declared immutable."""
    prov = get_provenance(skill_name)
    if prov["source"] != "managed" or not prov["immutable_fields"]:
        return False
    immutable = set(json.loads(prov["immutable_fields"]))
    return bool(immutable & changed_fields)


# --- Management state (status / global enablement / audit verdict / forced) ---


def get_state(skill_name: str) -> dict[str, Any]:
    """Return management state; skills with no row default to active/enabled."""
    row = (
        _database()
        .execute(
            "SELECT skill_name, status, global_enabled, audit_verdict, audit_rules, "
            "forced, archived_at, updated_at FROM skill_admin_state "
            "WHERE skill_name = :skill_name",
            {"skill_name": skill_name},
        )
        .fetchone()
    )
    if row is None:
        return {
            "skill_name": skill_name,
            "status": "active",
            "global_enabled": 1,
            "audit_verdict": None,
            "audit_rules": None,
            "forced": 0,
            "archived_at": None,
            "updated_at": None,
        }
    return row


def list_states(include_archived: bool = False) -> list[dict[str, Any]]:
    """Return all management-state rows; archived excluded unless asked."""
    sql = (
        "SELECT skill_name, status, global_enabled, audit_verdict, audit_rules, "
        "forced, archived_at, updated_at FROM skill_admin_state"
    )
    if not include_archived:
        sql += " WHERE status != 'archived'"
    return _database().execute(sql + " ORDER BY skill_name").fetchall()


def set_audit_result(skill_name: str, verdict: str, rules: list[str] | None = None) -> None:
    """Persist the latest security-audit verdict and matched rules for a skill."""
    _upsert_state(
        skill_name,
        {"audit_verdict": verdict, "audit_rules": json.dumps(rules) if rules else None},
    )


def set_status(skill_name: str, status: str) -> None:
    """Set lifecycle status: active / archived / quarantined."""
    if status not in {"active", "archived", "quarantined"}:
        raise ValueError(f"unknown status: {status}")
    extra: dict[str, str | None] = {"status": status}
    extra["archived_at"] = _now() if status == "archived" else None
    _upsert_state(skill_name, extra)


def set_global_enabled(skill_name: str, enabled: bool) -> None:
    """Globally enable/disable a skill (engine stops/starts matching it)."""
    _upsert_state(skill_name, {"global_enabled": 1 if enabled else 0})


def set_forced(skill_name: str, forced: bool) -> None:
    """Mark a skill as force-published despite a suspicious/rejected verdict."""
    _upsert_state(skill_name, {"forced": 1 if forced else 0})


_STATE_DEFAULTS = {
    "status": "active",
    "global_enabled": 1,
    "audit_verdict": None,
    "audit_rules": None,
    "forced": 0,
    "archived_at": None,
}


def _upsert_state(skill_name: str, fields: dict[str, Any]) -> None:
    merged = {**_STATE_DEFAULTS, **fields, "skill_name": skill_name, "updated_at": _now()}
    assignments = ", ".join(f"{k} = :{k}" for k in fields)
    with _database().transaction() as conn:
        conn.execute(
            f"""
            INSERT INTO skill_admin_state
                (skill_name, status, global_enabled, audit_verdict, audit_rules,
                 forced, archived_at, updated_at)
            VALUES (:skill_name, :status, :global_enabled, :audit_verdict, :audit_rules,
                    :forced, :archived_at, :updated_at)
            ON CONFLICT(skill_name) DO UPDATE SET {assignments}, updated_at = :updated_at
            """,
            merged,
        )


# --- Hit tracking (skill-observability-tracking) ------------------------------


def observe(skill_name: str) -> dict[str, Any]:
    """Per-skill observability from the agent-side trace: hit count + deduped sessions.

    Reads ``skill_hit`` trace events written by the agent runtime to observability, rather
    than a platform-owned table — honoring the agent->platform data-flow direction (the
    platform reads agent products; the agent never writes platform tables). ``stale`` is
    False because this is live data.
    """
    from fleetent.observability.traces import TraceQuery, query_trace_events

    hits = 0
    sessions: set[str] = set()
    for event in query_trace_events(TraceQuery(event_type="skill_hit", limit=100_000)):
        if event.payload.get("skill_name") != skill_name:
            continue
        hits += 1
        if event.session_id:
            sessions.add(event.session_id)
    return {
        "skill_name": skill_name,
        "hits": hits,
        "sessions": sorted(sessions),
        "stale": False,
    }
