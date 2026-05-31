"""Long-term context construction for agent prompts."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fleetent import memory_layer
from fleetent.config import Settings
from fleetent.intelligence import knowledge_base

_MEMORY_LIMIT = 10
_KNOWLEDGE_LIMIT = 10


@dataclass(frozen=True)
class ContextSource:
    """Summary of a source injected into long-term context."""

    source_type: str
    source_id: str
    score: float
    metadata: dict[str, str]


@dataclass(frozen=True)
class BuiltContext:
    """Long-term context text and the sources used to build it."""

    text: str
    sources: list[ContextSource]


KnowledgeProvider = Callable[[str, str, str, int], Awaitable[list[object]]]

_knowledge_provider: KnowledgeProvider | None = None


def set_knowledge_provider(provider: KnowledgeProvider | None) -> None:
    """Set the optional knowledge search provider used by build_context()."""

    global _knowledge_provider
    _knowledge_provider = provider


async def build_context(
    user_id: str,
    query: str,
    agent_id: str,
    available_tokens: int,
) -> BuiltContext:
    """Build injectable long-term context from memory and optional knowledge sources."""

    if available_tokens <= 0:
        return BuiltContext(text="", sources=[])

    memories = await memory_layer.search(user_id, query, limit=_MEMORY_LIMIT)
    knowledge_results = await _search_knowledge(user_id, query, agent_id, _KNOWLEDGE_LIMIT)
    if not memories and not knowledge_results:
        return BuiltContext(text="", sources=[])

    budget = min(available_tokens, Settings(anthropic_api_key="").long_term_ctx.max_tokens)
    lines: list[str] = []
    sources: list[ContextSource] = []

    if memories:
        memory_lines = ["[Long-term memory]"]
        memory_sources: list[ContextSource] = []
        for memory in memories:
            memory_lines.append(f"- {memory.content}")
            memory_sources.append(
                ContextSource(
                    source_type="memory",
                    source_id=memory.id,
                    score=1.0,
                    metadata={"type": memory.type},
                )
            )
        _append_section(lines, sources, memory_lines, memory_sources, budget)

    if knowledge_results:
        knowledge_lines = ["[Knowledge]"]
        knowledge_sources: list[ContextSource] = []
        for item in knowledge_results:
            knowledge_lines.append(f"- {_item_content(item)}")
            knowledge_sources.append(_knowledge_source(item))
        _append_section(lines, sources, knowledge_lines, knowledge_sources, budget)

    return BuiltContext(text="\n".join(lines), sources=sources)


def _append_section(
    lines: list[str],
    sources: list[ContextSource],
    section_lines: list[str],
    section_sources: list[ContextSource],
    budget: int,
) -> None:
    candidate_lines = [*lines]
    if candidate_lines:
        candidate_lines.append("")
    candidate_lines.extend(section_lines)
    if len("\n".join(candidate_lines)) <= budget:
        lines[:] = candidate_lines
        sources.extend(section_sources)


def _item_content(item: object) -> str:
    return str(getattr(item, "content", ""))


async def _search_knowledge(
    user_id: str,
    query: str,
    agent_id: str,
    limit: int,
) -> list[object]:
    if _knowledge_provider is not None:
        return await _knowledge_provider(user_id, query, agent_id, limit)

    settings = Settings(anthropic_api_key="")
    if not settings.knowledge_base.enabled:
        return []
    results = await knowledge_base.search(
        query,
        tenant_id=settings.knowledge_base.default_tenant_id,
        kb_ids=[settings.knowledge_base.default_kb_id],
        limit=limit,
    )
    return list(results)


def _knowledge_source(item: object) -> ContextSource:
    raw_metadata = getattr(item, "metadata", {})
    metadata: dict[str, str] = (
        {str(key): str(value) for key, value in raw_metadata.items()}
        if isinstance(raw_metadata, dict)
        else {}
    )
    if not metadata and hasattr(item, "filename"):
        metadata = {
            "filename": str(getattr(item, "filename", "")),
            "document_id": str(getattr(item, "document_id", "")),
            "kb_id": str(getattr(item, "kb_id", "")),
        }
    return ContextSource(
        source_type="knowledge",
        source_id=str(getattr(item, "id", "")),
        score=float(getattr(item, "score", 1.0)),
        metadata=metadata,
    )
