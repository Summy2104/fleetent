"""Long-term context construction for agent prompts."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Literal

import httpx

from fleetent import memory
from fleetent.config import LongTermContextSettings, Settings
from fleetent.db import SQLiteDatabase, create_database
from fleetent.identity import INGRESS_PRINCIPAL_HEADER, Principal, encode_ingress_principal
from fleetent.knowledge_base.core import KnowledgeStore
from fleetent.knowledge_base.core.models import KnowledgeChunk
from fleetent.knowledge_base.errors import KnowledgeBaseEmbeddingMismatchError
from fleetent.knowledge_base.planner import KnowledgeSearchOptions, KnowledgeSearchPlan
from fleetent.knowledge_base.retrieval.search import SearchMode
from fleetent.knowledge_base.retrieval.search import search as kb_search
from fleetent.memory import agent_memory
from fleetent.observability import KBRetrievalAuditContext
from fleetent.structured_logging import get_logger

_MEMORY_LIMIT = 10
_KNOWLEDGE_LIMIT = 10

_logger = get_logger("long_term_ctx")


# ── indirection seams for always-facts (monkeypatchable in unit tests) ────────


def _list_always_facts(user_id: str) -> list[Any]:
    from fleetent.memory import facts_store

    return facts_store.list_always_facts(user_id)


async def _search_facts_situational(user_id: str, query: str, limit: int) -> list[Any]:
    return await memory.search_facts(user_id, query, limit=limit)


async def _search_agent_memory(query: str, limit: int) -> list[Any]:
    return await agent_memory.search_agent_memory(query, limit=limit)


async def _search_knowledge_seam(
    user_id: str,
    query: str,
    agent_id: str,
    limit: int,
    audit_context: Any = None,
) -> list[Any]:
    return await _search_knowledge(user_id, query, agent_id, limit, audit_context=audit_context)


# Alias exposed for monkeypatching in tests
_search_knowledge_ref = _search_knowledge_seam


async def _retrieve_with_timeout[T](
    name: str,
    coro_factory: Callable[[], Awaitable[T]],
    *,
    timeout: float,
    empty: T,
) -> T:
    """Run one retrieval path under a timeout, degrading to ``empty`` on failure.

    Returns the path's result on success.  On timeout OR any exception the path
    is degraded to ``empty`` and a warning is logged (never re-raised) so one
    stalled/failing path cannot block or crash the others.  Per-path latency and
    outcome are logged for "which path was slow" diagnosis.
    """
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(coro_factory(), timeout)
        _logger.info(
            "ltc_retrieval_path",
            path=name,
            elapsed_ms=round((time.monotonic() - started) * 1000, 1),
            timed_out=False,
        )
        return result
    except TimeoutError:
        _logger.warn(
            "ltc_retrieval_timeout",
            path=name,
            elapsed_ms=round((time.monotonic() - started) * 1000, 1),
            timeout_s=timeout,
        )
        return empty
    except KnowledgeBaseEmbeddingMismatchError as exc:
        _logger.warn(
            "ltc_retrieval_hard_failed",
            path=name,
            error_type=type(exc).__name__,
            error=str(exc),
            elapsed_ms=round((time.monotonic() - started) * 1000, 1),
        )
        raise
    except Exception as exc:  # noqa: BLE001 — one path's failure must not break the others
        _logger.warn(
            "ltc_retrieval_failed",
            path=name,
            error_type=type(exc).__name__,
            error=str(exc),
            elapsed_ms=round((time.monotonic() - started) * 1000, 1),
        )
        return empty


ConflictPreference = Literal["auto", "memory", "knowledge", "agent_memory"]


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
    agent_memory_used_tokens: int = 0
    decisions: list[BudgetDecision] = field(default_factory=list)


@dataclass(frozen=True)
class BudgetPolicy:
    """Resolved budget policy for long-term context source selection."""

    max_tokens: int
    memory_max_tokens: int
    knowledge_max_tokens: int
    agent_memory_max_tokens: int
    memory_top_k: int
    knowledge_top_k: int
    agent_memory_top_k: int
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


KnowledgeProvider = Callable[
    [Principal, str, list[str], int, KBRetrievalAuditContext | None],
    Awaitable[list[KnowledgeChunk]],
]


# Back-compat seam for existing monkeypatch-based unit and integration tests that
# patch ``long_term_ctx.knowledge_base.search``.
async def _kb_search_compat(
    query: str,
    tenant_id: str | None = None,
    kb_ids: list[str] | None = None,
    limit: int = 10,
    mode: SearchMode = "vector",
    audit_context: KBRetrievalAuditContext | None = None,
) -> list[object]:
    return list(
        await kb_search(
            query,
            store=KnowledgeStore(_database()),
            tenant_id=tenant_id,
            kb_ids=kb_ids,
            limit=limit,
            mode=mode,
            audit_context=audit_context,
        )
    )


def _plan_knowledge_search_compat(
    query: str, options: KnowledgeSearchOptions
) -> KnowledgeSearchPlan:
    from fleetent.knowledge_base import plan_knowledge_search

    return plan_knowledge_search(query, options)


async def _execute_knowledge_search_plan_compat(plan: KnowledgeSearchPlan) -> list[object]:
    from fleetent.knowledge_base import execute_knowledge_search_plan

    return list(await execute_knowledge_search_plan(plan))


knowledge_base = SimpleNamespace(
    search=_kb_search_compat,
    plan_knowledge_search=_plan_knowledge_search_compat,
    execute_knowledge_search_plan=_execute_knowledge_search_plan_compat,
)


class LocalKnowledgeProvider:
    """Default knowledge provider backed by the local knowledge base."""

    async def __call__(
        self,
        principal: Principal,
        query: str,
        kb_ids: list[str],
        limit: int,
        audit_context: KBRetrievalAuditContext | None,
    ) -> list[KnowledgeChunk]:
        if not kb_ids:
            return []

        from fleetent import agent_config

        agent = agent_config.active_agent_or_default()
        policy = agent.knowledge.retrieval_policy
        use_planner = bool(getattr(policy, "use_planner", False))
        if use_planner:
            plan = knowledge_base.plan_knowledge_search(
                query,
                KnowledgeSearchOptions(
                    tenant_id=principal.tenant_id,
                    kb_ids=kb_ids,
                    limit=limit,
                    rerank=bool(getattr(policy, "rerank", False)),
                ),
            )
            return list(await knowledge_base.execute_knowledge_search_plan(plan))

        return list(
            await knowledge_base.search(
                query,
                tenant_id=principal.tenant_id,
                kb_ids=kb_ids,
                limit=limit,
                mode=policy.mode,
                audit_context=audit_context,
            )
        )


def _knowledge_chunk_to_wire_dict(chunk: KnowledgeChunk) -> dict[str, object]:
    return {
        "id": chunk.id,
        "document_id": chunk.document_id,
        "tenant_id": chunk.tenant_id,
        "kb_id": chunk.kb_id,
        "filename": chunk.filename,
        "content": chunk.content,
        "position": chunk.position,
        "score": chunk.score,
        "source": chunk.source,
        "source_url": chunk.source_url,
        "metadata": dict(chunk.metadata),
    }


def _knowledge_chunk_from_wire_dict(payload: dict[str, object]) -> KnowledgeChunk:
    raw_metadata = payload.get("metadata", {})
    metadata = (
        {str(key): str(value) for key, value in raw_metadata.items()}
        if isinstance(raw_metadata, dict)
        else {}
    )
    return KnowledgeChunk(
        id=str(payload["id"]),
        document_id=str(payload["document_id"]),
        tenant_id=str(payload["tenant_id"]),
        kb_id=str(payload["kb_id"]),
        filename=str(payload["filename"]),
        content=str(payload["content"]),
        position=int(payload["position"]),
        score=float(payload["score"]),
        source=str(payload["source"]),
        source_url=str(payload["source_url"]) if payload.get("source_url") is not None else None,
        metadata=metadata,
    )


class HttpKnowledgeProvider:
    """Knowledge provider backed by a remote HTTP retrieval endpoint."""

    def __init__(
        self,
        url: str,
        *,
        service_key: str,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._service_key = service_key
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def __call__(
        self,
        principal: Principal,
        query: str,
        kb_ids: list[str],
        limit: int,
        audit_context: KBRetrievalAuditContext | None,
    ) -> list[KnowledgeChunk]:
        del audit_context
        headers = {
            "Authorization": f"Bearer {self._service_key}",
            INGRESS_PRINCIPAL_HEADER: encode_ingress_principal(principal),
        }
        from fleetent import agent_config

        policy = agent_config.active_agent_or_default().knowledge.retrieval_policy
        payload = {
            "principal": {"user_id": principal.user_id, "tenant_id": principal.tenant_id},
            "query": query,
            "kb_ids": kb_ids,
            "limit": limit,
            "mode": policy.mode,
            "rerank": bool(getattr(policy, "rerank", False)),
            "use_planner": bool(getattr(policy, "use_planner", False)),
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(self._url, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
            return [
                _knowledge_chunk_from_wire_dict(item)
                for item in body.get("chunks", [])
                if isinstance(item, dict)
            ]
        except httpx.HTTPError as exc:
            _logger.warn(
                "http_knowledge_provider_failed",
                url=self._url,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return []


_default_knowledge_provider = LocalKnowledgeProvider()
_knowledge_provider: KnowledgeProvider | None = None


def set_knowledge_provider(provider: KnowledgeProvider | None) -> None:
    """Set the optional knowledge search provider used by build_context()."""

    global _knowledge_provider
    _knowledge_provider = provider


def _ltc_config() -> "LongTermContextSettings":
    """long_term_ctx config from the active agent (a neutral default when absent).

    Resolves the active single-agent process's ``long_term_ctx`` block, or a neutral
    default ``AgentFile``'s block when no single agent is published."""
    from fleetent import agent_config

    return agent_config.active_agent_or_default().long_term_ctx


async def build_context(
    user_id: str,
    query: str,
    agent_id: str,
    available_tokens: int,
    audit_context: KBRetrievalAuditContext | None = None,
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

    # Always-scope facts: unconditional injection — pure SQL, no vector, no timeout.
    # Run synchronously before the concurrent retrieval so they are always present
    # regardless of whether the vector paths degrade. Best-effort: DB not yet wired
    # (unit tests, eval harness) must not break the run.
    try:
        always_facts = _list_always_facts(user_id)
    except Exception:
        always_facts = []
    always_candidates = [_always_fact_candidate(f) for f in always_facts]

    # Retrieve across all subjects (user / agent / third parties). Each fact's
    # statement names its subject explicitly, so the model can tell whose fact it
    # is without us filtering by subject (which would hide agent/third-party facts).
    #
    # The three paths are independent and each hits an external embedding proxy
    # that can stall; run them concurrently under a per-path timeout so a single
    # slow path degrades to empty instead of blocking the whole reply. A degraded
    # (empty) path is equivalent to "no hits" for the downstream merge/budget.
    timeout = _ltc_config().retrieval_timeout_seconds
    memories, knowledge_results, agent_memory_results = await asyncio.gather(
        _retrieve_with_timeout(
            "memory",
            lambda: _search_facts_situational(user_id, query, _MEMORY_LIMIT),
            timeout=timeout,
            empty=[],
        ),
        _retrieve_with_timeout(
            "knowledge",
            lambda: _search_knowledge(
                user_id, query, agent_id, _KNOWLEDGE_LIMIT, audit_context=audit_context
            ),
            timeout=timeout,
            empty=[],
        ),
        _retrieve_with_timeout(
            "agent_memory",
            lambda: _search_agent_memory(query, policy.agent_memory_top_k),
            timeout=timeout,
            empty=[],
        ),
    )
    if (
        not always_candidates
        and not memories
        and not knowledge_results
        and not agent_memory_results
    ):
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
    agent_memory_candidates = sorted(
        (_agent_memory_candidate(item) for item in agent_memory_results),
        key=lambda candidate: (-candidate.source.score, candidate.source.source_id),
    )
    selection = _select_candidates(
        _ordered_candidates(
            query=query,
            policy=policy,
            memory_candidates=memory_candidates,
            knowledge_candidates=knowledge_candidates,
            agent_memory_candidates=agent_memory_candidates,
        ),
        policy=policy,
    )

    return BuiltContext(
        text=_render_context_with_always(always_candidates, selection.included),
        sources=[candidate.source for candidate in always_candidates]
        + [candidate.source for candidate in selection.included],
        budget_metadata=BudgetMetadata(
            effective_budget=policy.max_tokens,
            memory_used_tokens=selection.memory_used_tokens,
            knowledge_used_tokens=selection.knowledge_used_tokens,
            agent_memory_used_tokens=selection.agent_memory_used_tokens,
            decisions=selection.decisions,
        ),
    )


def _resolve_policy(available_tokens: int) -> BudgetPolicy:
    settings = _ltc_config()
    return BudgetPolicy(
        max_tokens=min(available_tokens, settings.max_tokens),
        memory_max_tokens=settings.memory_max_tokens,
        knowledge_max_tokens=settings.knowledge_max_tokens,
        agent_memory_max_tokens=settings.agent_memory_max_tokens,
        memory_top_k=settings.memory_top_k,
        knowledge_top_k=settings.knowledge_top_k,
        agent_memory_top_k=settings.agent_memory_top_k,
        conflict_preference=settings.conflict_preference,
    )


@dataclass(frozen=True)
class _Selection:
    included: list[_ContextCandidate]
    decisions: list[BudgetDecision]
    memory_used_tokens: int
    knowledge_used_tokens: int
    agent_memory_used_tokens: int


def _select_candidates(candidates: list[_ContextCandidate], *, policy: BudgetPolicy) -> _Selection:
    included: list[_ContextCandidate] = []
    decisions: list[BudgetDecision] = []
    included_by_type = {"memory": 0, "knowledge": 0, "agent_memory": 0}
    used_by_type = {"memory": 0, "knowledge": 0, "agent_memory": 0}

    for candidate in candidates:
        source_type = candidate.source.source_type
        if source_type == "memory":
            top_k = policy.memory_top_k
            source_budget = policy.memory_max_tokens
        elif source_type == "agent_memory":
            top_k = policy.agent_memory_top_k
            source_budget = policy.agent_memory_max_tokens
        else:
            top_k = policy.knowledge_top_k
            source_budget = policy.knowledge_max_tokens
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
        agent_memory_used_tokens=used_by_type["agent_memory"],
    )


def _ordered_candidates(
    *,
    query: str,
    policy: BudgetPolicy,
    memory_candidates: list[_ContextCandidate],
    knowledge_candidates: list[_ContextCandidate],
    agent_memory_candidates: list[_ContextCandidate],
) -> list[_ContextCandidate]:
    preference = policy.conflict_preference
    if preference == "auto":
        preference = _infer_conflict_preference(query)
    if preference == "knowledge":
        return [*knowledge_candidates, *agent_memory_candidates, *memory_candidates]
    if preference == "agent_memory":
        return [*agent_memory_candidates, *memory_candidates, *knowledge_candidates]
    # "memory" and default
    return [*memory_candidates, *agent_memory_candidates, *knowledge_candidates]


def _infer_conflict_preference(query: str) -> Literal["memory", "knowledge", "agent_memory"]:
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


_SECTION_HEADERS = {
    "memory": "[Long-term memory — 你记住的关于用户的事实]",
    "agent_memory": "[Agent memory — 你自己的记忆笔记]",
    "knowledge": "[Knowledge — 知识库检索结果]",
}

_ALWAYS_SECTION_HEADER = "[Behavioral directives — 始终生效的行为规则]"


def _render_context(candidates: list[_ContextCandidate]) -> str:
    lines: list[str] = []
    active_section = ""
    for candidate in candidates:
        source_type = candidate.source.source_type
        if source_type != active_section:
            if lines:
                lines.append("")
            lines.append(_SECTION_HEADERS.get(source_type, "[Knowledge]"))
            active_section = source_type
        lines.append(candidate.line)
    return "\n".join(lines)


def _render_context_with_always(
    always_candidates: list[_ContextCandidate],
    situational_candidates: list[_ContextCandidate],
) -> str:
    """Render always-scope facts first (unconditional), then situational candidates."""
    parts: list[str] = []
    if always_candidates:
        parts.append(_ALWAYS_SECTION_HEADER)
        for candidate in always_candidates:
            parts.append(candidate.line)
    situational_text = _render_context(situational_candidates)
    if situational_text:
        if parts:
            parts.append("")
        parts.append(situational_text)
    return "\n".join(parts)


def _always_fact_candidate(fact: Any) -> _ContextCandidate:
    """Build a context candidate for an always-scope fact (score=1.0, no vector)."""
    if fact.statement:
        line = f"- {fact.statement}"
    else:
        line = f"- {_subject_phrase(fact.subject)} {fact.relation}: {fact.object}"
    return _ContextCandidate(
        source=ContextSource(
            source_type="memory",
            source_id=fact.fact_id,
            score=1.0,
            metadata={"relation": fact.relation, "scope": "always"},
            token_estimate=len(line),
        ),
        line=line,
        token_estimate=len(line),
    )


def _subject_phrase(subject: str) -> str:
    """Render a fact subject as a possessive phrase for context lines.

    'user' → "The user's"; 'agent' → "Your"; a named third party → "{name}'s".
    """
    if subject == "user":
        return "The user's"
    if subject == "agent":
        return "Your"
    return f"{subject}'s"


def _memory_candidate(result: Any) -> _ContextCandidate:
    """Build a context candidate from a facts SearchResult (fact + score).

    Prefer the fact's ``statement`` — an LLM-written sentence with an explicit
    subject ("用户的名字是 Xin") — so the model never mistakes a fact ABOUT the
    user for one about itself.  Pre-statement rows (statement IS NULL) fall back
    to a subject-qualified join of the triple.
    """
    fact = result.fact
    if fact.statement:
        line = f"- {fact.statement}"
    else:
        line = f"- {_subject_phrase(fact.subject)} {fact.relation}: {fact.object}"
    return _ContextCandidate(
        source=ContextSource(
            source_type="memory",
            source_id=fact.fact_id,
            score=result.score,
            metadata={"relation": fact.relation},
            token_estimate=len(line),
        ),
        line=line,
        token_estimate=len(line),
    )


def _agent_memory_candidate(item: agent_memory.AgentMemoryItem) -> _ContextCandidate:
    line = f"- {item.content}"
    return _ContextCandidate(
        source=ContextSource(
            source_type="agent_memory",
            source_id=item.id,
            score=1.0,
            metadata={"type": item.type},
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
    audit_context: KBRetrievalAuditContext | None = None,
) -> list[KnowledgeChunk]:

    from fleetent import agent_config

    agent = agent_config.active_agent_or_default()
    kb = agent.knowledge
    if not kb.enabled:
        return []
    bindings = [binding for binding in kb.bindings if binding.permissions.search]
    kb_ids = [binding.kb_id for binding in bindings]
    if not kb_ids:
        return []
    tenant_id = kb.tenant_id
    if tenant_id is None:
        raise ValueError("knowledge.bindings must all share the same tenant_id")
    principal = Principal(user_id=user_id, tenant_id=tenant_id)
    provider = _knowledge_provider or _default_knowledge_provider
    return list(await provider(principal, query, kb_ids, limit, audit_context))


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


def _database() -> SQLiteDatabase:
    # In the agent process, _init_agent_db_schema wires _kb_db to the per-tenant kb.db at
    # boot; prefer it so retrieval reads the right tenant KB instead of the management DB.
    from fleetent.knowledge_base import runtime as _kb_runtime

    kb_db = _kb_runtime._kb_db
    if kb_db is not None:
        return kb_db
    return create_database(Settings().database_url)
