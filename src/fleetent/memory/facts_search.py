"""Semantic search over user memory facts.

Vector retrieval returns candidate fact ids; the SQL layer filters to active
facts and (when relevance clears the gate) updates access counters.  A turn
whose best match scores below ACCESS_GATE is treated as unrelated chatter:
results are still returned, but no access counters move — this is what lets a
short-term fact's 30-day idle window actually expire instead of being kept
alive by every passing conversation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fleetent.memory.facts_models import Fact, SearchResult
from fleetent.vector_store.namespaces import memory_namespace
from fleetent.vector_store.runtime import embed_text

logger = logging.getLogger(__name__)

# Below this max cosine score, the turn is unrelated → do not touch access counters.
ACCESS_GATE = 0.5

# Upgrade a short-term fact to long-term once it is both frequently and durably used.
UPGRADE_MIN_ACCESS = 10
UPGRADE_MIN_AGE = timedelta(days=14)


async def search_facts(
    user_id: str,
    query: str,
    *,
    limit: int = 10,
    subject: str | None = None,
    vector_backend: object,
) -> list[SearchResult]:
    """Return active facts semantically relevant to query, in vector order.

    The per-user memory space holds facts about multiple subjects (the user
    themselves, the agent, named third parties).  Pass ``subject`` to restrict
    results to one subject (e.g. ``subject="user"`` when building the user's own
    profile so agent/third-party facts don't leak in); omit it to span all.

    When the best score reaches ACCESS_GATE, access counters for the returned
    facts are bumped (and eligible facts upgraded to long-term).
    """
    query_vector = await embed_text(query)
    namespace = memory_namespace(user_id)
    # Over-fetch so post-filter (active-only, optional subject) still leaves enough.
    fetch = max(limit * 2, limit) if subject is None else max(limit * 4, limit)
    hits = await vector_backend.search(query_vector, namespace, fetch)  # type: ignore[attr-defined]
    if not hits:
        return []

    by_id = _facts_by_ids([hit.id for hit in hits])
    results: list[SearchResult] = []
    for hit in hits:
        fact = by_id.get(hit.id)
        if fact is None or fact.status != "active":
            continue
        if subject is not None and fact.subject != subject:
            continue
        results.append(SearchResult(fact=fact, score=hit.score))
        if len(results) >= limit:
            break

    max_score = max((hit.score for hit in hits), default=0.0)
    if max_score >= ACCESS_GATE and results:
        now = datetime.now(UTC).replace(microsecond=0)
        _update_access([r.fact.fact_id for r in results], now)

    return results


# Indirection seams — kept as module-level functions so search_facts can be unit
# tested by monkeypatching them without a real DB.


def _facts_by_ids(ids: list[str]) -> dict[str, Fact]:
    from fleetent.memory import facts_store

    return facts_store.facts_by_ids(ids)


def _update_access(fact_ids: list[str], now: datetime) -> None:
    """Bump access counters for the given facts and upgrade eligible ones.

    Best-effort: a DB failure here is logged, not raised — the search result has
    already been returned to the caller.
    """
    from fleetent.memory import facts_store

    for fact_id in fact_ids:
        try:
            facts_store.update_fact_access(fact_id, now)
            _maybe_upgrade(fact_id, now)
        except Exception:
            logger.warning("facts_search: access update failed for fact %s", fact_id, exc_info=True)


def _maybe_upgrade(fact_id: str, now: datetime) -> None:
    """Set expires_at = NULL (long-term) when access count and age both clear bars."""
    from fleetent.memory import facts_store

    fact = facts_store.get_fact(fact_id)
    if fact is None or fact.expires_at is None:
        return  # already long-term or gone
    if fact.access_count < UPGRADE_MIN_ACCESS:
        return
    if fact.first_accessed_at is None or fact.first_accessed_at > now - UPGRADE_MIN_AGE:
        return
    facts_store.set_fact_expires_at(fact_id, None)
