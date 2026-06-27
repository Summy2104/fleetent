"""Lifecycle operations for user memory facts: archive, pin, retract.

archive_expired_facts is the background sweep; pin/retract are user-initiated.
All status changes are soft (the row is never hard-deleted) so the supersedes
history stays intact.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from fleetent.db import SQLiteDatabase
from fleetent.memory import facts_store
from fleetent.memory.store import format_datetime
from fleetent.vector_store.namespaces import memory_namespace

logger = logging.getLogger(__name__)

# A short-term fact not retrieved within this window is archived even if its
# expires_at has not yet passed.
IDLE_WINDOW = timedelta(days=30)

# Default sweep cadence for the background archive job.
DEFAULT_SWEEP_INTERVAL = 3600.0

_sweep_task: asyncio.Task[None] | None = None


async def archive_expired_facts(
    db: SQLiteDatabase,
    vector_backend: object,
    *,
    now: datetime | None = None,
) -> int:
    """Archive short-term facts that have expired or gone idle.

    A fact is archived when it is active, short-term (expires_at IS NOT NULL),
    and either expires_at has passed or it has not been accessed within
    IDLE_WINDOW (falling back to created_at when never accessed).  Long-term
    facts (expires_at IS NULL) are never touched.  Returns the count archived.
    """
    now = now or datetime.now(UTC).replace(microsecond=0)
    idle_cutoff = now - IDLE_WINDOW

    result = db.execute(
        """
        SELECT fact_id, user_id FROM memory_items
        WHERE status = 'active'
          AND expires_at IS NOT NULL
          AND (
              expires_at <= :now
              OR COALESCE(last_accessed_at, created_at) <= :idle_cutoff
          )
        """,
        {"now": format_datetime(now), "idle_cutoff": format_datetime(idle_cutoff)},
    )
    rows = result.rows
    if not rows:
        return 0

    db.execute(
        """
        UPDATE memory_items
        SET status = 'archived', updated_at = :now
        WHERE status = 'active'
          AND expires_at IS NOT NULL
          AND (
              expires_at <= :now
              OR COALESCE(last_accessed_at, created_at) <= :idle_cutoff
          )
        """,
        {"now": format_datetime(now), "idle_cutoff": format_datetime(idle_cutoff)},
    )

    for row in rows:
        await _delete_vector(row["user_id"], row["fact_id"], vector_backend)
    return len(rows)


async def _archive_sweep_loop(db: SQLiteDatabase, vector_backend: object, interval: float) -> None:
    """Periodically archive expired/idle short-term facts (bare asyncio loop).

    Each iteration is fault-isolated: a single sweep failure is logged and the
    loop continues, mirroring session maintenance.  A failure here must never
    kill the resident task or change the process exit code.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            archived = await archive_expired_facts(db, vector_backend)
            if archived:
                logger.info("facts_lifecycle: archived %d expired/idle facts", archived)
        except Exception:  # noqa: BLE001 — a single failure must not kill the loop
            logger.error("facts_lifecycle: archive sweep iteration failed", exc_info=True)


def start_archive_sweep(
    db: SQLiteDatabase,
    vector_backend: object,
    *,
    interval: float = DEFAULT_SWEEP_INTERVAL,
) -> asyncio.Task[None]:
    """Start the background archive sweep task.  Idempotent."""
    global _sweep_task
    if _sweep_task is not None and not _sweep_task.done():
        return _sweep_task
    _sweep_task = asyncio.create_task(_archive_sweep_loop(db, vector_backend, interval))
    return _sweep_task


async def stop_archive_sweep() -> None:
    """Cancel the background archive sweep task, leaving no residual task."""
    global _sweep_task
    if _sweep_task is None:
        return
    _sweep_task.cancel()
    with suppress(asyncio.CancelledError):
        await _sweep_task
    _sweep_task = None


def pin_fact(fact_id: str) -> None:
    """Promote a fact to long-term by setting expires_at = NULL.

    Raises ValueError if the fact is not active.
    """
    fact = facts_store.get_fact(fact_id)
    if fact is None:
        raise ValueError("fact does not exist")
    if fact.status != "active":
        raise ValueError("cannot pin non-active fact")
    facts_store.set_fact_expires_at(fact_id, None)


async def retract_fact(fact_id: str, *, vector_backend: object) -> None:
    """Mark a fact retracted (user actively denied it) and drop its vector."""
    fact = facts_store.get_fact(fact_id)
    if fact is None:
        raise ValueError("fact does not exist")
    facts_store.update_fact_status(fact_id, "retracted")
    await _delete_vector(fact.user_id, fact_id, vector_backend)


async def retract_by_relation(
    user_id: str,
    subject: str,
    relation: str,
    *,
    vector_backend: object,
) -> int:
    """Retract every active fact for a user + subject + relation.  Returns count."""
    facts = facts_store.active_facts_for_relation(user_id, subject, relation)
    for fact in facts:
        facts_store.update_fact_status(fact.fact_id, "retracted")
        await _delete_vector(user_id, fact.fact_id, vector_backend)
    return len(facts)


async def _delete_vector(user_id: str, fact_id: str, vector_backend: object) -> None:
    if vector_backend is None:
        return
    try:
        namespace = memory_namespace(user_id)
        await vector_backend.delete(fact_id, namespace)  # type: ignore[attr-defined]
    except Exception:
        logger.warning("facts_lifecycle: vector delete failed for fact %s", fact_id, exc_info=True)
