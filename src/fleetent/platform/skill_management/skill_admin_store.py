"""Management-face persistence for Skill administration.

The platform skill admin surface owns two management tables after migration 092:

- ``skills``: the catalog/master metadata row keyed by skill name.
- ``agent_skills``: the Skill↔Agent binding matrix plus per-agent deployment state.

Schema lifecycle is owned by Alembic; this module never creates tables.
"""

import datetime
import json
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteConnection, SQLiteDatabase, create_database


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _ensure_skill_row(conn: SQLiteConnection, skill_name: str) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO skills (
            name, status, global_enabled, audit_verdict, audit_rules, forced, source,
            immutable_fields, current_version, archived_at, created_at, updated_at
        )
        VALUES (
            :skill_name, 'active', 1, NULL, NULL, 0, 'adhoc',
            NULL, NULL, NULL, :created_at, :updated_at
        )
        ON CONFLICT(name) DO NOTHING
        """,
        {"skill_name": skill_name, "created_at": now, "updated_at": now},
    )


_STATE_DEFAULTS = {
    "status": "active",
    "global_enabled": 1,
    "audit_verdict": None,
    "audit_rules": None,
    "forced": 0,
    "archived_at": None,
}


def _state_row_default(skill_name: str) -> dict[str, Any]:
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


# --- Skill ↔ Agent binding matrix ---------------------------------------------


def set_binding(agent_id: int, skill_name: str, enabled: bool, updated_by: str | None) -> None:
    """Upsert the enablement of ``skill_name`` for ``agent_id`` (idempotent)."""
    with _database().transaction() as conn:
        _ensure_skill_row(conn, skill_name)
        conn.execute(
            """
            INSERT INTO agent_skills (
                agent_id, skill_name, enabled, updated_at, updated_by, base_version, drift, drift_at
            )
            VALUES (
                :agent_id, :skill_name, :enabled, :updated_at, :updated_by, NULL, 0, NULL
            )
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
            """
            SELECT
                agent_id, skill_name, enabled, updated_at, updated_by, base_version, drift, drift_at
            FROM agent_skills
            WHERE skill_name = :skill_name
            ORDER BY agent_id
            """,
            {"skill_name": skill_name},
        )
        .fetchall()
    )


def list_skills_for_agent(agent_id: int) -> list[dict[str, Any]]:
    """Return every skill binding for an agent, enabled or not."""
    return (
        _database()
        .execute(
            """
            SELECT
                agent_id, skill_name, enabled, updated_at, updated_by, base_version, drift, drift_at
            FROM agent_skills
            WHERE agent_id = :agent_id
            ORDER BY skill_name
            """,
            {"agent_id": agent_id},
        )
        .fetchall()
    )


def has_any_binding(agent_id: int) -> bool:
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


def enabled_skill_names(agent_id: int) -> set[str]:
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


def agents_enabling(skill_name: str) -> list[int]:
    """Return agent ids that explicitly enable the skill — drives delete protection."""
    rows = (
        _database()
        .execute(
            """
            SELECT agent_id
            FROM agent_skills
            WHERE skill_name = :skill_name AND enabled = 1
            ORDER BY agent_id
            """,
            {"skill_name": skill_name},
        )
        .fetchall()
    )
    return [int(r["agent_id"]) for r in rows]


# --- Catalog metadata ---------------------------------------------------------


def set_source(skill_name: str, source: str, immutable_fields: list[str] | None = None) -> None:
    """Record the catalog source and immutable field set for a skill."""
    if source not in {"managed", "adhoc"}:
        raise ValueError(f"unknown source: {source}")
    with _database().transaction() as conn:
        _ensure_skill_row(conn, skill_name)
        conn.execute(
            """
            UPDATE skills
            SET source = :source,
                immutable_fields = :immutable_fields,
                updated_at = :updated_at
            WHERE name = :skill_name
            """,
            {
                "skill_name": skill_name,
                "source": source,
                "immutable_fields": json.dumps(immutable_fields) if immutable_fields else None,
                "updated_at": _now(),
            },
        )


def get_source(skill_name: str) -> dict[str, Any]:
    """Return catalog source/current_version metadata for a skill."""
    row = (
        _database()
        .execute(
            """
            SELECT name AS skill_name, source, immutable_fields, current_version
            FROM skills
            WHERE name = :skill_name
            """,
            {"skill_name": skill_name},
        )
        .fetchone()
    )
    if row is None:
        return {
            "skill_name": skill_name,
            "source": "adhoc",
            "immutable_fields": None,
            "current_version": None,
        }
    return row


def ensure_catalog_entries(skill_names: list[str]) -> None:
    """Ensure the skills catalog has rows for every listed skill."""
    with _database().transaction() as conn:
        for skill_name in skill_names:
            _ensure_skill_row(conn, skill_name)


# --- Per-agent deployment state ----------------------------------------------


def set_drift(agent_id: int, skill_name: str, *, drifted: bool) -> None:
    """Record whether an agent's deployed copy has drifted from the pool copy."""
    with _database().transaction() as conn:
        now = _now()
        conn.execute(
            """
            UPDATE agent_skills
            SET drift = :drift,
                drift_at = :drift_at,
                updated_at = :updated_at
            WHERE agent_id = :agent_id AND skill_name = :skill_name
            """,
            {
                "agent_id": agent_id,
                "skill_name": skill_name,
                "drift": 1 if drifted else 0,
                "drift_at": now if drifted else None,
                "updated_at": now,
            },
        )


def get_drift(agent_id: int, skill_name: str) -> dict[str, Any]:
    """Return per-agent drift/base_version state for a bound skill."""
    row = (
        _database()
        .execute(
            """
            SELECT agent_id, skill_name, base_version, drift, drift_at
            FROM agent_skills
            WHERE agent_id = :agent_id AND skill_name = :skill_name
            """,
            {"agent_id": agent_id, "skill_name": skill_name},
        )
        .fetchone()
    )
    if row is None:
        return {
            "agent_id": agent_id,
            "skill_name": skill_name,
            "base_version": None,
            "drift": 0,
            "drift_at": None,
        }
    return row


def set_base_version(agent_id: int, skill_name: str, base_version: str | None) -> None:
    """Persist the pool version an agent copy was last materialized from."""
    with _database().transaction() as conn:
        now = _now()
        conn.execute(
            """
            UPDATE agent_skills
            SET base_version = :base_version,
                updated_at = :updated_at
            WHERE agent_id = :agent_id AND skill_name = :skill_name
            """,
            {
                "agent_id": agent_id,
                "skill_name": skill_name,
                "base_version": base_version,
                "updated_at": now,
            },
        )


def drifted_agents(skill_name: str) -> list[int]:
    """Return agent ids whose deployed skill copy is marked drifted."""
    rows = (
        _database()
        .execute(
            """
            SELECT agent_id
            FROM agent_skills
            WHERE skill_name = :skill_name AND drift = 1
            ORDER BY agent_id
            """,
            {"skill_name": skill_name},
        )
        .fetchall()
    )
    return [int(row["agent_id"]) for row in rows]


# --- Management state (status / global enablement / audit verdict / forced) ---


def get_state(skill_name: str) -> dict[str, Any]:
    """Return management state; skills with no row default to active/enabled."""
    row = (
        _database()
        .execute(
            """
            SELECT
                name AS skill_name,
                status,
                global_enabled,
                audit_verdict,
                audit_rules,
                forced,
                archived_at,
                updated_at
            FROM skills
            WHERE name = :skill_name
            """,
            {"skill_name": skill_name},
        )
        .fetchone()
    )
    return row if row is not None else _state_row_default(skill_name)


def list_states(include_archived: bool = False) -> list[dict[str, Any]]:
    """Return all catalog-state rows; archived excluded unless asked."""
    sql = (
        "SELECT name AS skill_name, status, global_enabled, audit_verdict, audit_rules, "
        "forced, archived_at, updated_at FROM skills"
    )
    if not include_archived:
        sql += " WHERE status != 'archived'"
    return _database().execute(sql + " ORDER BY name").fetchall()


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


def _upsert_state(skill_name: str, fields: dict[str, Any]) -> None:
    merged = {
        **_STATE_DEFAULTS,
        "source": "adhoc",
        "immutable_fields": None,
        "current_version": None,
        "created_at": _now(),
        **fields,
        "skill_name": skill_name,
        "updated_at": _now(),
    }
    assignments = ", ".join(f"{key} = :{key}" for key in fields)
    with _database().transaction() as conn:
        conn.execute(
            f"""
            INSERT INTO skills (
                name, status, global_enabled, audit_verdict, audit_rules, forced, source,
                immutable_fields, current_version, archived_at, created_at, updated_at
            )
            VALUES (
                :skill_name, :status, :global_enabled, :audit_verdict, :audit_rules,
                :forced, :source,
                :immutable_fields, :current_version, :archived_at, :created_at, :updated_at
            )
            ON CONFLICT(name) DO UPDATE SET {assignments}, updated_at = :updated_at
            """,
            merged,
        )


# --- Hit tracking (skill-observability-tracking) ------------------------------


def observe(skill_name: str) -> dict[str, Any]:
    """Per-skill observability from the agent-side trace: hit count + deduped sessions."""
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
