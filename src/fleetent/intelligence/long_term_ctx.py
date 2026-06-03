"""Long-term context construction for agent prompts."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from fleetent.config import Settings
from fleetent.intelligence import knowledge_base, long_term_ctx_policy, memory
from fleetent.intelligence.long_term_ctx_policy import (
    AgentContextIdentity as AgentContextIdentity,
)
from fleetent.intelligence.long_term_ctx_policy import (
    ContextPolicy as ContextPolicy,
)
from fleetent.intelligence.long_term_ctx_policy import (
    ContextPolicySourceBudget as ContextPolicySourceBudget,
)
from fleetent.intelligence.long_term_ctx_policy import (
    resolve_context_policy as resolve_context_policy,
)

_MEMORY_LIMIT = 10
_KNOWLEDGE_LIMIT = 10

_POLICY_SECTION_HEADERS = {
    "user_memory": "[Long-term memory]",
    "knowledge_base": "[Knowledge]",
    "tenant_shared_memory": "[Shared memory: tenant]",
    "team_shared_memory": "[Shared memory: team]",
}

ConflictPreference = Literal["auto", "memory", "knowledge"]


@dataclass(frozen=True)
class ContextSource:
    """Summary of a source injected into long-term context."""

    source_type: str
    source_id: str
    score: float
    metadata: dict[str, str]
    token_estimate: int = 0


@dataclass(frozen=True)
class BudgetDecision:
    """Decision made while applying long-term context budget policy."""

    source_type: str
    source_id: str
    token_estimate: int
    reason: str
    included: bool


@dataclass(frozen=True)
class BudgetMetadata:
    """Budget accounting for a built long-term context."""

    effective_budget: int = 0
    memory_used_tokens: int = 0
    knowledge_used_tokens: int = 0
    decisions: list[BudgetDecision] = field(default_factory=list)


@dataclass(frozen=True)
class BudgetPolicy:
    """Resolved budget policy for long-term context source selection."""

    max_tokens: int
    memory_max_tokens: int
    knowledge_max_tokens: int
    memory_top_k: int
    knowledge_top_k: int
    conflict_preference: ConflictPreference = "auto"


@dataclass(frozen=True)
class BuiltContext:
    """Long-term context text and the sources used to build it."""

    text: str
    sources: list[ContextSource]
    budget_metadata: BudgetMetadata = field(default_factory=BudgetMetadata)


@dataclass(frozen=True)
class _ContextCandidate:
    source: ContextSource
    line: str
    token_estimate: int


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
    memory_namespace: str = "default",
) -> BuiltContext:
    """Build injectable long-term context from memory and optional knowledge sources."""

    if available_tokens <= 0:
        return BuiltContext(
            text="",
            sources=[],
            budget_metadata=BudgetMetadata(
                effective_budget=0,
                decisions=[
                    BudgetDecision(
                        source_type="budget",
                        source_id="available_tokens",
                        token_estimate=0,
                        reason="zero_available_tokens",
                        included=False,
                    )
                ],
            ),
        )

    policy = _resolve_policy(available_tokens)
    memories = await memory.search(user_id, query, limit=_MEMORY_LIMIT, namespace=memory_namespace)
    knowledge_results = await _search_knowledge(user_id, query, agent_id, _KNOWLEDGE_LIMIT)
    if not memories and not knowledge_results:
        return BuiltContext(
            text="",
            sources=[],
            budget_metadata=BudgetMetadata(effective_budget=policy.max_tokens),
        )

    memory_candidates = sorted(
        (_memory_candidate(memory) for memory in memories),
        key=lambda candidate: (-candidate.source.score, candidate.source.source_id),
    )
    knowledge_candidates = sorted(
        (_knowledge_candidate(item) for item in knowledge_results),
        key=lambda candidate: (-candidate.source.score, candidate.source.source_id),
    )
    selection = _select_candidates(
        _ordered_candidates(
            query=query,
            policy=policy,
            memory_candidates=memory_candidates,
            knowledge_candidates=knowledge_candidates,
        ),
        policy=policy,
    )

    return BuiltContext(
        text=_render_context(selection.included),
        sources=[candidate.source for candidate in selection.included],
        budget_metadata=BudgetMetadata(
            effective_budget=policy.max_tokens,
            memory_used_tokens=selection.memory_used_tokens,
            knowledge_used_tokens=selection.knowledge_used_tokens,
            decisions=selection.decisions,
        ),
    )


async def build_context_with_policy(
    *,
    identity: AgentContextIdentity,
    user_id: str,
    query: str,
    available_tokens: int,
) -> BuiltContext:
    """Build long-term context honoring the agent's resolved context policy.

    Resolves the tenant/agent policy, queries only enabled sources (deriving the
    Shared Memory scope from agent ownership), and records budget decisions for
    disabled or skipped sources.
    """
    if available_tokens <= 0:
        return BuiltContext(
            text="",
            sources=[],
            budget_metadata=BudgetMetadata(
                effective_budget=0,
                decisions=[
                    BudgetDecision(
                        source_type="budget",
                        source_id="available_tokens",
                        token_estimate=0,
                        reason="zero_available_tokens",
                        included=False,
                    )
                ],
            ),
        )

    policy = long_term_ctx_policy.resolve_context_policy(identity)
    total_budget = min(available_tokens, Settings(anthropic_api_key="").long_term_ctx.max_tokens)

    decisions: list[BudgetDecision] = []
    included: list[_ContextCandidate] = []
    used_by_source: dict[str, int] = {}

    for source in sorted(policy.sources, key=lambda s: s.priority):
        if not source.enabled:
            decisions.append(_policy_decision(source.source, "disabled_by_policy"))
            continue
        candidates, skip_reason = await _policy_source_candidates(
            source.source, identity, user_id, query, source.top_k
        )
        if skip_reason is not None:
            decisions.append(_policy_decision(source.source, skip_reason))
            continue
        candidates.sort(key=lambda candidate: (-candidate.source.score, candidate.source.source_id))
        included_count = 0
        for candidate in candidates:
            reason = ""
            if included_count >= source.top_k:
                reason = "source_top_k_exceeded"
            elif (
                used_by_source.get(source.source, 0) + candidate.token_estimate > source.max_tokens
            ):
                reason = "source_budget_exceeded"
            elif len(_render_policy_context([*included, candidate])) > total_budget:
                reason = "total_budget_exceeded"
            if reason:
                decisions.append(_decision(candidate, included=False, reason=reason))
                continue
            included.append(candidate)
            included_count += 1
            used_by_source[source.source] = (
                used_by_source.get(source.source, 0) + candidate.token_estimate
            )
            decisions.append(_decision(candidate, included=True, reason="included"))

    return BuiltContext(
        text=_render_policy_context(included),
        sources=[candidate.source for candidate in included],
        budget_metadata=BudgetMetadata(effective_budget=total_budget, decisions=decisions),
    )


def _policy_decision(source: str, reason: str) -> BudgetDecision:
    return BudgetDecision(
        source_type=source,
        source_id="policy",
        token_estimate=0,
        reason=reason,
        included=False,
    )


async def _policy_source_candidates(
    source: str,
    identity: AgentContextIdentity,
    user_id: str,
    query: str,
    top_k: int,
) -> tuple[list[_ContextCandidate], str | None]:
    if source == "user_memory":
        memories = await memory.search(user_id, query, limit=top_k)
        return _ranked_candidates(
            source, [(item.id, item.content, {"type": item.type}) for item in memories]
        ), None
    if source == "knowledge_base":
        results = await _search_knowledge(user_id, query, identity.agent_id, top_k)
        return [_policy_knowledge_candidate(item) for item in results], None
    if source == "tenant_shared_memory":
        tenant_items = await memory.search_shared_memory("tenant", identity.tenant_id, query, top_k)
        return _ranked_candidates(source, [_shared_row(item) for item in tenant_items]), None
    if source == "team_shared_memory":
        if not identity.team_id:
            return [], "team_id_missing"
        team_items = await memory.search_shared_memory("team", identity.team_id, query, top_k)
        return _ranked_candidates(source, [_shared_row(item) for item in team_items]), None
    return [], None


def _shared_row(item: memory.SharedMemoryItem) -> tuple[str, str, dict[str, str]]:
    return item.id, item.content, _shared_metadata(item)


def _shared_metadata(item: memory.SharedMemoryItem) -> dict[str, str]:
    return {"type": item.type, "scope_type": item.scope_type, "scope_id": item.scope_id}


def _ranked_candidates(
    source: str, rows: list[tuple[str, str, dict[str, str]]]
) -> list[_ContextCandidate]:
    # Preserve provider relevance order via descending rank scores.
    total = len(rows)
    candidates: list[_ContextCandidate] = []
    for index, (source_id, content, metadata) in enumerate(rows):
        line = f"- {content}"
        candidates.append(
            _ContextCandidate(
                source=ContextSource(
                    source_type=source,
                    source_id=source_id,
                    score=float(total - index),
                    metadata=metadata,
                    token_estimate=len(line),
                ),
                line=line,
                token_estimate=len(line),
            )
        )
    return candidates


def _policy_knowledge_candidate(item: object) -> _ContextCandidate:
    content = _item_content(item)
    line = f"- {content}"
    source = _knowledge_source(item)
    return _ContextCandidate(
        source=ContextSource(
            source_type="knowledge_base",
            source_id=source.source_id,
            score=source.score,
            metadata=source.metadata,
            token_estimate=len(line),
        ),
        line=line,
        token_estimate=len(line),
    )


def _render_policy_context(candidates: list[_ContextCandidate]) -> str:
    lines: list[str] = []
    active_section = ""
    for candidate in candidates:
        source_type = candidate.source.source_type
        if source_type != active_section:
            if lines:
                lines.append("")
            lines.append(_POLICY_SECTION_HEADERS.get(source_type, f"[{source_type}]"))
            active_section = source_type
        lines.append(candidate.line)
    return "\n".join(lines)


def _resolve_policy(available_tokens: int) -> BudgetPolicy:
    settings = Settings(anthropic_api_key="").long_term_ctx
    return BudgetPolicy(
        max_tokens=min(available_tokens, settings.max_tokens),
        memory_max_tokens=settings.memory_max_tokens,
        knowledge_max_tokens=settings.knowledge_max_tokens,
        memory_top_k=settings.memory_top_k,
        knowledge_top_k=settings.knowledge_top_k,
        conflict_preference=settings.conflict_preference,
    )


@dataclass(frozen=True)
class _Selection:
    included: list[_ContextCandidate]
    decisions: list[BudgetDecision]
    memory_used_tokens: int
    knowledge_used_tokens: int


def _select_candidates(candidates: list[_ContextCandidate], *, policy: BudgetPolicy) -> _Selection:
    included: list[_ContextCandidate] = []
    decisions: list[BudgetDecision] = []
    included_by_type = {"memory": 0, "knowledge": 0}
    used_by_type = {"memory": 0, "knowledge": 0}

    for candidate in candidates:
        source_type = candidate.source.source_type
        top_k = policy.memory_top_k if source_type == "memory" else policy.knowledge_top_k
        source_budget = (
            policy.memory_max_tokens if source_type == "memory" else policy.knowledge_max_tokens
        )
        reason = ""
        if candidate.source.score <= 0:
            reason = "below_relevance_threshold"
        elif included_by_type[source_type] >= top_k:
            reason = "source_top_k_exceeded"
        elif used_by_type[source_type] + candidate.token_estimate > source_budget:
            reason = "source_budget_exceeded"
        elif len(_render_context([*included, candidate])) > policy.max_tokens:
            reason = "total_budget_exceeded"

        if reason:
            decisions.append(_decision(candidate, included=False, reason=reason))
            continue

        included.append(candidate)
        included_by_type[source_type] += 1
        used_by_type[source_type] += candidate.token_estimate
        decisions.append(_decision(candidate, included=True, reason="included"))

    return _Selection(
        included=included,
        decisions=decisions,
        memory_used_tokens=used_by_type["memory"],
        knowledge_used_tokens=used_by_type["knowledge"],
    )


def _ordered_candidates(
    *,
    query: str,
    policy: BudgetPolicy,
    memory_candidates: list[_ContextCandidate],
    knowledge_candidates: list[_ContextCandidate],
) -> list[_ContextCandidate]:
    preference = policy.conflict_preference
    if preference == "auto":
        preference = _infer_conflict_preference(query)
    if preference == "knowledge":
        return [*knowledge_candidates, *memory_candidates]
    return [*memory_candidates, *knowledge_candidates]


def _infer_conflict_preference(query: str) -> Literal["memory", "knowledge"]:
    normalized = query.casefold()
    personal_markers = (
        " my ",
        " i ",
        " me ",
        "remember",
        "preference",
        "prefer",
        "history",
        "我",
        "我的",
        "偏好",
        "记得",
    )
    factual_markers = (
        "what",
        "where",
        "when",
        "how",
        "policy",
        "procedure",
        "process",
        "handbook",
        "document",
        "docs",
        "reference",
        "流程",
        "制度",
        "文档",
        "规定",
    )
    padded = f" {normalized} "
    if any(marker in padded for marker in personal_markers):
        return "memory"
    if any(marker in padded for marker in factual_markers):
        return "knowledge"
    return "memory"


def _decision(candidate: _ContextCandidate, *, included: bool, reason: str) -> BudgetDecision:
    return BudgetDecision(
        source_type=candidate.source.source_type,
        source_id=candidate.source.source_id,
        token_estimate=candidate.token_estimate,
        reason=reason,
        included=included,
    )


def _render_context(candidates: list[_ContextCandidate]) -> str:
    lines: list[str] = []
    active_section = ""
    for candidate in candidates:
        source_type = candidate.source.source_type
        if source_type != active_section:
            if lines:
                lines.append("")
            lines.append("[Long-term memory]" if source_type == "memory" else "[Knowledge]")
            active_section = source_type
        lines.append(candidate.line)
    return "\n".join(lines)


def _memory_candidate(memory_item: memory.MemoryItem) -> _ContextCandidate:
    line = f"- {memory_item.content}"
    return _ContextCandidate(
        source=ContextSource(
            source_type="memory",
            source_id=memory_item.id,
            score=1.0,
            metadata={"type": memory_item.type},
            token_estimate=len(line),
        ),
        line=line,
        token_estimate=len(line),
    )


def _knowledge_candidate(item: object) -> _ContextCandidate:
    content = _item_content(item)
    line = f"- {content}"
    source = _knowledge_source(item)
    return _ContextCandidate(
        source=ContextSource(
            source_type=source.source_type,
            source_id=source.source_id,
            score=source.score,
            metadata=source.metadata,
            token_estimate=len(line),
        ),
        line=line,
        token_estimate=len(line),
    )


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
    kb_ids = knowledge_base.resolve_agent_kb_ids(
        settings.knowledge_base.default_tenant_id,
        agent_id,
    )
    if not kb_ids:
        return []
    results = await knowledge_base.search(
        query,
        tenant_id=settings.knowledge_base.default_tenant_id,
        kb_ids=kb_ids,
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
