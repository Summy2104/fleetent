"""Public User Memory API.

The facts-based triple system (subject/relation/object) is the canonical
user memory store.  Use ``run_pipeline`` (write) and ``search_facts`` (read),
plus ``pin_fact`` / ``retract_fact`` for user-initiated lifecycle.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fleetent.memory.agent_memory import (
    apply_agent_memory_proposal,
    archive_agent_memory,
    create_agent_memory,
    iter_indexable_agent_memories,
    list_agent_memory,
    search_agent_memory,
    update_agent_memory,
)
from fleetent.memory.facts_lifecycle import pin_fact, retract_fact
from fleetent.memory.facts_pipeline import run_pipeline
from fleetent.memory.facts_store import list_active_facts, set_facts_db
from fleetent.memory.models import (
    AgentMemoryItem,
    AgentMemorySource,
    AgentMemoryStatus,
    AgentMemoryType,
)


def iter_indexable_memories(user_id: str) -> Iterator[Any]:
    """Yield active user memory facts as IndexableItem for vector reindex.

    Replaces the legacy free-text MemoryItem iteration; now iterates the
    facts-based triple store so the vector index stays in sync with memory_items.
    """
    from fleetent import vector_store
    from fleetent.memory.facts_models import fact_index_text
    from fleetent.memory.facts_store import list_active_facts
    from fleetent.vector_store.namespaces import memory_namespace

    ns = memory_namespace(user_id)
    for fact in list_active_facts(user_id):
        text = fact_index_text(fact)
        yield vector_store.IndexableItem(
            id=fact.fact_id,
            content=text,
            namespace=ns,
            metadata={"relation": fact.relation, "subject": fact.subject},
        )


async def search_facts(
    user_id: str, query: str, *, limit: int = 10, subject: str | None = None
) -> list[Any]:
    """Retrieve relevant active facts for a user.

    Convenience wrapper that pulls the per-agent vector backend injected at boot
    (via ``set_facts_db``) so callers need not thread the backend through.  Pass
    ``subject`` (e.g. "user") to restrict to one fact subject.
    """
    from fleetent.memory import facts_search, facts_store

    return await facts_search.search_facts(
        user_id,
        query,
        limit=limit,
        subject=subject,
        vector_backend=facts_store._facts_vector_backend,
    )


__all__ = [
    "AgentMemoryItem",
    "AgentMemorySource",
    "AgentMemoryStatus",
    "AgentMemoryType",
    "apply_agent_memory_proposal",
    "archive_agent_memory",
    "create_agent_memory",
    "iter_indexable_agent_memories",
    "iter_indexable_memories",
    "list_agent_memory",
    "list_active_facts",
    "pin_fact",
    "retract_fact",
    "run_pipeline",
    "search_agent_memory",
    "search_facts",
    "set_facts_db",
    "update_agent_memory",
]
