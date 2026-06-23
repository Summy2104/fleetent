"""Platform read-only projection of agent-side databases (§7 implementation).

Platform reads agent-side physical databases through read-only connections only —
never writing, never migrating. Discovery uses the management.db registry
(agent_store); each agent's DB is opened via router.agent_scope(...).open_state_db_ro()
which returns a ReadOnlySQLiteDatabase.

Aggregation happens at the application layer; no materialized views, no data
is copied into platform tables.

Design constraints (3d):
- platform → read-only agent libs: allowed direction
- agent ✗→ platform: strictly forbidden (this module respects that)
- Reads never trigger migrate (open_*_ro never sets user_version)
- No materialized copies; platform reads live agent files directly
"""

from __future__ import annotations

from typing import Any

from fleetent.tenant_router import TenantRouter


def aggregate_session_counts_across_agents(
    router: TenantRouter,
    agents: list[tuple[str, str]],
) -> int:
    """Return total session count across all given (tenant_id, agent_id) pairs.

    Opens each agent's state_db read-only; no migration is triggered.  Agents
    whose DB file does not exist yet (never booted) are silently skipped.

    Args:
        router: Initialized TenantRouter pointing at the data directory.
        agents: List of (tenant_id, agent_id) tuples from the registry.

    Returns:
        Sum of session counts across all accessible agent DBs.
    """
    import sqlite3

    from fleetent.session import index as session_index

    total = 0
    for tenant_id, agent_id in agents:
        scope = router.agent_scope(tenant_id, agent_id)
        try:
            ro_db = scope.open_state_db_ro()
            total += session_index.count_with_db(ro_db)
        except sqlite3.OperationalError:
            # DB file doesn't exist — agent never booted; skip silently
            pass
    return total


def aggregate_approvals_across_agents(
    router: TenantRouter,
    agents: list[tuple[str, str]],
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Return approval records across all given (tenant_id, agent_id) pairs.

    Each record is enriched with agent_id so the caller can identify the source.
    Opens each agent's state_db read-only; agents whose DB does not exist are skipped.

    Args:
        router: Initialized TenantRouter pointing at the data directory.
        agents: List of (tenant_id, agent_id) tuples from the registry.
        status: Optional status filter ('pending', 'approved', 'rejected', etc.).

    Returns:
        Merged list of approval dicts, each carrying an ``agent_id`` field.
    """
    import sqlite3

    from fleetent.governance import approval_store

    results: list[dict[str, Any]] = []
    for tenant_id, agent_id in agents:
        scope = router.agent_scope(tenant_id, agent_id)
        try:
            ro_db = scope.open_state_db_ro()
            rows = approval_store.list_approvals_with_db(ro_db, status=status)
            for row in rows:
                enriched = dict(row)
                enriched["agent_id"] = agent_id
                enriched["tenant_id"] = tenant_id
                results.append(enriched)
        except sqlite3.OperationalError:
            pass
    return results


def aggregate_trace_events_across_agents(
    router: TenantRouter,
    agents: list[tuple[str, int]],
    *,
    event_type: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Return trace events across platform agents using the read translation boundary.

    Each input pair is a platform-side ``(tenant_id, agent_id)``. The function resolves
    the readable agent name from the management registry, opens that agent's state DB
    read-only, reads its name-keyed traces, and enriches each event with the platform
    ``agent_id`` so callers stay on the management identity model.
    """
    import sqlite3

    from fleetent import agent_store

    results: list[dict[str, Any]] = []
    params: dict[str, object] = {"limit": limit}
    where = ""
    if event_type is not None:
        where = "WHERE event_type = :event_type"
        params["event_type"] = event_type

    for tenant_id, agent_id in agents:
        agent_name = agent_store.get_agent_name_by_id(agent_id)
        if agent_name is None:
            continue
        scope = router.agent_scope(tenant_id, agent_name)
        try:
            ro_db = scope.open_state_db_ro()
            rows = ro_db.execute(
                f"""
                SELECT
                    id, run_id, span_id, parent_span_id, session_id, user_id, agent_name,
                    tenant_id, event_type, ts, payload_json
                FROM traces
                {where}
                ORDER BY ts ASC
                LIMIT :limit
                """,
                params,
            ).fetchall()
            for row in rows:
                enriched = dict(row)
                enriched["agent_id"] = agent_id
                results.append(enriched)
        except sqlite3.OperationalError:
            pass
    return results


def read_agent_memory_for_agents(
    router: TenantRouter,
    agents: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Return agent memory items across per-agent agent_memory.db files (read-only).

    Each record is enriched with ``agent_id`` so the caller can identify the source.
    Opens each agent's agent_memory.db read-only; agents whose DB does not exist are skipped.

    Args:
        router: Initialized TenantRouter pointing at the data directory.
        agents: List of (tenant_id, agent_id) tuples to read from.

    Returns:
        Merged list of agent memory item dicts, each carrying an ``agent_id`` field.
    """
    import sqlite3

    results: list[dict[str, Any]] = []
    for tenant_id, agent_id in agents:
        scope = router.agent_scope(tenant_id, agent_id)
        try:
            ro_db = scope.open_agent_memory_db_ro()
            rows = ro_db.execute(
                "SELECT * FROM agent_memory_items ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
            for row in rows:
                enriched = dict(row)
                enriched["agent_id"] = agent_id
                results.append(enriched)
        except sqlite3.OperationalError:
            pass
    return results
