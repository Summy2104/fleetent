from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fleetent import agent_config
from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models
from fleetent.config import LongTermContextSettings
from fleetent.identity import Principal
from fleetent.knowledge_base import KnowledgeChunk
from fleetent.knowledge_base.retrieval.graph_search import GraphSearchChunk, GraphSearchResult
from fleetent.memory.facts_models import Fact, SearchResult
from fleetent.observability import KBRetrievalAuditContext


def _publish_agent(monkeypatch, agent: AgentFile) -> None:
    monkeypatch.setattr(
        agent_config,
        "_index",
        AgentConfigIndex(agents={agent.name: agent}, default=agent.name),
    )


def _mem_result(
    object_text: str,
    fact_id: str = "mem-1",
    *,
    relation: str = "has_preference",
    subject: str = "user",
    statement: str | None = None,
    score: float = 0.9,
) -> SearchResult:
    now = datetime.now(UTC)
    return SearchResult(
        fact=Fact(
            fact_id=fact_id,
            user_id="user-1",
            subject=subject,
            relation=relation,
            object=object_text,
            cardinality="multi",
            status="active",
            access_count=0,
            first_accessed_at=None,
            last_accessed_at=None,
            expires_at=None,
            valid_until=None,
            created_at=now,
            updated_at=now,
            source_turn=None,
            statement=statement,
        ),
        score=score,
    )


def _kb_chunk(
    chunk_id: str,
    content: str,
    *,
    score: float = 0.82,
    tenant_id: str = "tenant-a",
    kb_id: str = "global",
) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=chunk_id,
        document_id=f"doc-{chunk_id}",
        tenant_id=tenant_id,
        kb_id=kb_id,
        filename=f"{chunk_id}.md",
        content=content,
        position=0,
        score=score,
        source="manual",
        source_url=None,
    )


async def test_public_api_is_importable():
    from fleetent.long_term_ctx import BuiltContext, ContextSource, build_context

    source = ContextSource(
        source_type="memory",
        source_id="mem-1",
        score=0.9,
        metadata={"type": "preference"},
    )
    context = BuiltContext(text="remembered context", sources=[source])

    assert context.text == "remembered context"
    assert context.sources == [source]
    assert callable(build_context)


async def test_zero_token_budget_returns_empty_context_without_provider_calls(monkeypatch):
    from fleetent import long_term_ctx

    memory_search = AsyncMock()
    knowledge_search = AsyncMock()
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", memory_search)
    long_term_ctx.set_knowledge_provider(knowledge_search)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="python",
        agent_id="agent-1",
        available_tokens=0,
    )

    assert result.text == ""
    assert result.sources == []
    memory_search.assert_not_awaited()
    knowledge_search.assert_not_awaited()


async def test_build_context_calls_memory_search_with_user_query_and_limit(monkeypatch):
    from fleetent import long_term_ctx

    memory_search = AsyncMock(return_value=[])
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", memory_search)
    long_term_ctx.set_knowledge_provider(None)

    await long_term_ctx.build_context(
        user_id="user-1",
        query="python debugging",
        agent_id="agent-1",
        available_tokens=200,
    )

    memory_search.assert_awaited_once_with("user-1", "python debugging", limit=10)


async def test_memory_results_are_formatted_with_memory_source_summary(monkeypatch):
    from fleetent import long_term_ctx

    memory = _mem_result("User prefers Python for backend services")
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[memory]))
    long_term_ctx.set_knowledge_provider(None)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="backend language",
        agent_id="agent-1",
        available_tokens=200,
    )

    assert "[Long-term memory" in result.text
    assert "User prefers Python for backend services" in result.text
    assert result.sources[0].source_type == "memory"
    assert result.sources[0].source_id == "mem-1"
    assert result.sources[0].metadata == {"relation": "has_preference"}


async def test_memory_injection_uses_statement_when_present(monkeypatch):
    from fleetent import long_term_ctx

    # An agent-subject fact whose statement names the subject explicitly must be
    # injected verbatim, so the model reads "用户希望助手回答简洁" not "agent tone: 简洁".
    memory = _mem_result(
        "简洁",
        relation="tone",
        subject="agent",
        statement="用户希望助手回答简洁",
    )
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[memory]))
    long_term_ctx.set_knowledge_provider(None)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="语气",
        agent_id="agent-1",
        available_tokens=200,
    )

    assert "用户希望助手回答简洁" in result.text
    # The raw triple join must NOT appear when a statement is available.
    assert "agent tone" not in result.text


async def test_missing_knowledge_provider_does_not_block_memory_context(monkeypatch):
    from fleetent import long_term_ctx

    memory = _mem_result("User works on fleetent")
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[memory]))
    long_term_ctx.set_knowledge_provider(None)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="project",
        agent_id="agent-1",
        available_tokens=200,
    )

    assert "User works on fleetent" in result.text
    assert "[Knowledge" not in result.text


async def test_builtin_knowledge_provider_uses_knowledge_base_search_when_enabled(monkeypatch):
    from fleetent import long_term_ctx

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
            },
        ),
    )
    chunk = KnowledgeChunk(
        id="chunk-1",
        document_id="doc-1",
        tenant_id="tenant-a",
        kb_id="global",
        filename="guide.md",
        content="Fleetent can ingest markdown knowledge.",
        position=0,
        score=0.82,
        source="manual",
        source_url=None,
    )
    knowledge_search = AsyncMock(return_value=[chunk])
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", knowledge_search)
    long_term_ctx.set_knowledge_provider(None)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="markdown",
        agent_id="agent-1",
        available_tokens=300,
    )

    knowledge_search.assert_awaited_once_with(
        "markdown",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=10,
        mode="hybrid",
        audit_context=None,
    )
    assert "[Knowledge" in result.text
    assert "Fleetent can ingest markdown knowledge." in result.text
    assert result.sources == [
        long_term_ctx.ContextSource(
            source_type="knowledge",
            source_id="chunk-1",
            score=0.82,
            metadata={"filename": "guide.md", "document_id": "doc-1", "kb_id": "global"},
            token_estimate=len("- Fleetent can ingest markdown knowledge."),
        )
    ]


async def test_local_knowledge_provider_keeps_search_path_equivalent_to_legacy_branch(monkeypatch):
    from fleetent import long_term_ctx
    from fleetent.identity import Principal

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
                "retrieval_policy": {"mode": "hybrid", "use_planner": False},
            },
        ),
    )
    legacy_chunk = _kb_chunk("legacy-search", "Legacy search result.")
    knowledge_search = AsyncMock(return_value=[legacy_chunk])
    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", knowledge_search)
    monkeypatch.setattr(
        long_term_ctx.knowledge_base,
        "plan_knowledge_search",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("planner must stay off")),
        raising=False,
    )
    monkeypatch.setattr(
        long_term_ctx.knowledge_base,
        "execute_knowledge_search_plan",
        AsyncMock(
            side_effect=AssertionError("planner execute must stay off when use_planner=false")
        ),
        raising=False,
    )

    provider = long_term_ctx.LocalKnowledgeProvider()
    audit = KBRetrievalAuditContext(run_id="run-1", tenant_id="tenant-a")
    results = await provider(
        Principal(user_id="user-1", tenant_id="tenant-a"),
        "markdown",
        ["global"],
        10,
        audit,
    )

    knowledge_search.assert_awaited_once_with(
        "markdown",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=10,
        mode="hybrid",
        audit_context=audit,
    )
    assert results == [legacy_chunk]


async def test_local_knowledge_provider_keeps_planner_path_equivalent_to_legacy_branch(
    monkeypatch,
):
    from fleetent import long_term_ctx
    from fleetent.identity import Principal
    from fleetent.knowledge_base import planner

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
                "retrieval_policy": {"mode": "hybrid", "use_planner": True},
            },
        ),
    )
    legacy_search = AsyncMock(return_value=[_kb_chunk("legacy-search", "legacy result")])
    planner_graph = AsyncMock(
        return_value=GraphSearchResult(
            query="Which service depends on Billing API?",
            tenant_id="tenant-a",
            kb_ids=["global"],
            depth=1,
            chunks=[
                GraphSearchChunk(
                    chunk=_kb_chunk("graph-hit", "Billing API depends on Auth Service."),
                    graph_score=1.0,
                    reason="relation_evidence",
                )
            ],
        )
    )
    planner_fill = AsyncMock(return_value=[])
    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", legacy_search)
    monkeypatch.setattr(planner, "graph_search", planner_graph)
    monkeypatch.setattr(planner, "search", planner_fill)

    provider = long_term_ctx.LocalKnowledgeProvider()
    results = await provider(
        Principal(user_id="user-1", tenant_id="tenant-a"),
        "Which service depends on Billing API?",
        ["global"],
        10,
        None,
    )

    legacy_search.assert_not_awaited()
    planner_graph.assert_awaited_once()
    planner_fill.assert_awaited_once()
    assert [chunk.id for chunk in results] == ["graph-hit"]


async def test_search_knowledge_resolves_scope_and_short_circuits_empty_bindings(monkeypatch):
    from fleetent import long_term_ctx
    from fleetent.identity import Principal

    provider = AsyncMock(return_value=[])
    long_term_ctx.set_knowledge_provider(provider)
    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [
                    {"tenant_id": "tenant-a", "kb_id": "global", "permissions": {"search": True}},
                    {"tenant_id": "tenant-a", "kb_id": "private", "permissions": {"search": False}},
                ],
            },
        ),
    )

    await long_term_ctx._search_knowledge("user-1", "markdown", "agent-1", 3)

    provider.assert_awaited_once_with(
        Principal(user_id="user-1", tenant_id="tenant-a"),
        "markdown",
        ["global"],
        3,
        None,
    )

    provider.reset_mock()
    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [
                    {"tenant_id": "tenant-a", "kb_id": "private", "permissions": {"search": False}}
                ],
            },
        ),
    )

    assert await long_term_ctx._search_knowledge("user-1", "markdown", "agent-1", 3) == []
    provider.assert_not_awaited()


async def test_search_knowledge_passes_principal_scope_and_audit_to_injected_provider(monkeypatch):
    from fleetent import long_term_ctx
    from fleetent.identity import Principal

    provider = AsyncMock(return_value=[])
    audit = KBRetrievalAuditContext(
        run_id="run-2",
        session_id="sess-2",
        user_id="user-1",
        agent_name="agent-1",
        tenant_id="tenant-a",
    )
    long_term_ctx.set_knowledge_provider(provider)
    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
            },
        ),
    )

    await long_term_ctx._search_knowledge(
        "user-1",
        "deployment",
        "agent-1",
        5,
        audit_context=audit,
    )

    provider.assert_awaited_once_with(
        Principal(user_id="user-1", tenant_id="tenant-a"),
        "deployment",
        ["global"],
        5,
        audit,
    )


async def test_build_context_degrades_when_provider_raises_and_keeps_other_sources(monkeypatch):
    from fleetent import long_term_ctx

    warnings: list[tuple[str, dict[str, object]]] = []

    class _FakeLogger:
        def warn(self, message: str, **fields: object) -> None:
            warnings.append((message, dict(fields)))

        def info(self, _message: str, **_fields: object) -> None:
            return None

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("kb backend down")

    monkeypatch.setattr(long_term_ctx, "_logger", _FakeLogger())
    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
            },
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search_facts",
        AsyncMock(return_value=[_mem_result("User prefers concise answers.")]),
    )
    monkeypatch.setattr(
        long_term_ctx.agent_memory,
        "search_agent_memory",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(long_term_ctx, "_list_always_facts", lambda _user_id: [])
    long_term_ctx.set_knowledge_provider(_boom)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="answer style",
        agent_id="agent-1",
        available_tokens=300,
    )

    assert "User prefers concise answers." in result.text
    assert [source.source_type for source in result.sources] == ["memory"]
    assert warnings[0][0] == "ltc_retrieval_failed"
    assert warnings[0][1]["path"] == "knowledge"
    assert warnings[0][1]["error_type"] == "RuntimeError"


async def test_build_context_degrades_when_provider_times_out_and_keeps_other_sources(monkeypatch):
    from fleetent import long_term_ctx

    warnings: list[tuple[str, dict[str, object]]] = []

    class _FakeLogger:
        def warn(self, message: str, **fields: object) -> None:
            warnings.append((message, dict(fields)))

        def info(self, _message: str, **_fields: object) -> None:
            return None

    async def _slow(*_args, **_kwargs):
        await asyncio.sleep(1.0)
        return []

    monkeypatch.setattr(long_term_ctx, "_logger", _FakeLogger())
    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
            },
        ),
    )
    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: LongTermContextSettings(retrieval_timeout_seconds=0.05),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search_facts",
        AsyncMock(return_value=[_mem_result("User prefers concise answers.")]),
    )
    monkeypatch.setattr(
        long_term_ctx.agent_memory,
        "search_agent_memory",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(long_term_ctx, "_list_always_facts", lambda _user_id: [])
    long_term_ctx.set_knowledge_provider(_slow)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="answer style",
        agent_id="agent-1",
        available_tokens=300,
    )

    assert "User prefers concise answers." in result.text
    assert [source.source_type for source in result.sources] == ["memory"]
    assert warnings[0][0] == "ltc_retrieval_timeout"
    assert warnings[0][1]["path"] == "knowledge"


async def test_build_context_propagates_kb_embedding_mismatch(monkeypatch):
    from fleetent import long_term_ctx
    from fleetent.knowledge_base.errors import KnowledgeBaseEmbeddingMismatchError

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
            },
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search_facts",
        AsyncMock(return_value=[_mem_result("User prefers concise answers.")]),
    )
    monkeypatch.setattr(
        long_term_ctx.agent_memory,
        "search_agent_memory",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(long_term_ctx, "_list_always_facts", lambda _user_id: [])

    async def _mismatch(*_args, **_kwargs):
        raise KnowledgeBaseEmbeddingMismatchError(
            "Knowledge base embedding mismatch for tenant-a/global"
        )

    long_term_ctx.set_knowledge_provider(_mismatch)

    with pytest.raises(
        KnowledgeBaseEmbeddingMismatchError, match="Knowledge base embedding mismatch"
    ):
        await long_term_ctx.build_context(
            user_id="user-1",
            query="answer style",
            agent_id="agent-1",
            available_tokens=300,
        )


async def test_builtin_knowledge_provider_keeps_search_path_when_planner_opt_in_is_false(
    monkeypatch,
):
    from fleetent import long_term_ctx

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
                "retrieval_policy": {"mode": "hybrid", "use_planner": False},
            },
        ),
    )
    legacy_chunk = _kb_chunk("legacy-search", "Legacy search result.")
    knowledge_search = AsyncMock(return_value=[legacy_chunk])
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", knowledge_search)
    monkeypatch.setattr(
        long_term_ctx.knowledge_base,
        "plan_knowledge_search",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("planner must stay off")),
        raising=False,
    )
    monkeypatch.setattr(
        long_term_ctx.knowledge_base,
        "execute_knowledge_search_plan",
        AsyncMock(
            side_effect=AssertionError("planner execute must stay off when use_planner=false")
        ),
        raising=False,
    )
    long_term_ctx.set_knowledge_provider(None)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="markdown",
        agent_id="agent-1",
        available_tokens=300,
    )

    knowledge_search.assert_awaited_once_with(
        "markdown",
        tenant_id="tenant-a",
        kb_ids=["global"],
        limit=10,
        mode="hybrid",
        audit_context=None,
    )
    assert "Legacy search result." in result.text
    assert [source.source_id for source in result.sources] == ["legacy-search"]


async def test_builtin_knowledge_provider_uses_planner_for_relation_like_queries(monkeypatch):
    from fleetent import long_term_ctx
    from fleetent.knowledge_base import planner

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
                "retrieval_policy": {"mode": "hybrid", "use_planner": True},
            },
        ),
    )
    legacy_search = AsyncMock(return_value=[_kb_chunk("legacy-search", "legacy result")])
    planner_graph = AsyncMock(
        return_value=GraphSearchResult(
            query="Which service depends on Billing API?",
            tenant_id="tenant-a",
            kb_ids=["global"],
            depth=1,
            chunks=[
                GraphSearchChunk(
                    chunk=_kb_chunk("graph-hit", "Billing API depends on Auth Service."),
                    graph_score=1.0,
                    reason="relation_evidence",
                )
            ],
        )
    )
    planner_fill = AsyncMock(return_value=[])
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", legacy_search)
    monkeypatch.setattr(planner, "graph_search", planner_graph)
    monkeypatch.setattr(planner, "search", planner_fill)
    long_term_ctx.set_knowledge_provider(None)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="Which service depends on Billing API?",
        agent_id="agent-1",
        available_tokens=300,
    )

    legacy_search.assert_not_awaited()
    planner_graph.assert_awaited_once()
    assert "Billing API depends on Auth Service." in result.text
    assert [source.source_id for source in result.sources] == ["graph-hit"]


async def test_builtin_knowledge_provider_planner_falls_back_to_hybrid_without_graph_data(
    monkeypatch,
):
    from fleetent import long_term_ctx
    from fleetent.knowledge_base import planner

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
                "retrieval_policy": {"mode": "hybrid", "use_planner": True},
            },
        ),
    )
    legacy_search = AsyncMock(return_value=[_kb_chunk("legacy-search", "legacy result")])
    planner_graph = AsyncMock(
        return_value=GraphSearchResult(
            query="Which service depends on Billing API?",
            tenant_id="tenant-a",
            kb_ids=["global"],
            depth=1,
            chunks=[],
        )
    )
    planner_fill = AsyncMock(
        return_value=[_kb_chunk("hybrid-fill", "Hybrid fallback answered the dependency query.")]
    )
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", legacy_search)
    monkeypatch.setattr(planner, "graph_search", planner_graph)
    monkeypatch.setattr(planner, "search", planner_fill)
    long_term_ctx.set_knowledge_provider(None)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="Which service depends on Billing API?",
        agent_id="agent-1",
        available_tokens=300,
    )

    legacy_search.assert_not_awaited()
    planner_graph.assert_awaited_once()
    planner_fill.assert_awaited_once()
    assert "Hybrid fallback answered the dependency query." in result.text
    assert [source.source_id for source in result.sources] == ["hybrid-fill"]


async def test_builtin_knowledge_provider_disabled_does_not_call_knowledge_base(monkeypatch):
    from fleetent import long_term_ctx

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={"enabled": False},
        ),
    )
    knowledge_search = AsyncMock(return_value=[])
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    monkeypatch.setattr(long_term_ctx.knowledge_base, "search", knowledge_search)
    long_term_ctx.set_knowledge_provider(None)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="markdown",
        agent_id="agent-1",
        available_tokens=300,
    )

    knowledge_search.assert_not_awaited()
    assert result.text == ""
    assert result.sources == []


async def test_build_context_keeps_budget_policy_path_for_memory_and_knowledge(monkeypatch):
    from fleetent import long_term_ctx

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
            },
        ),
    )
    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: LongTermContextSettings(
            max_tokens=200,
            memory_max_tokens=200,
            knowledge_max_tokens=200,
            memory_top_k=5,
            knowledge_top_k=5,
            conflict_preference="memory",
        ),
    )
    memory_item = _mem_result("User prefers on-prem deployment guidance.")
    knowledge_chunk = KnowledgeChunk(
        id="chunk-1",
        document_id="doc-1",
        tenant_id="tenant-a",
        kb_id="global",
        filename="guide.md",
        content="Fleetent supports self-hosted deployment.",
        position=0,
        score=0.82,
        source="manual",
        source_url=None,
    )
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[memory_item]))
    monkeypatch.setattr(
        long_term_ctx.knowledge_base, "search", AsyncMock(return_value=[knowledge_chunk])
    )
    long_term_ctx.set_knowledge_provider(None)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="deployment guide",
        agent_id="agent-1",
        available_tokens=200,
    )

    assert [source.source_type for source in result.sources] == ["memory", "knowledge"]
    assert result.budget_metadata.effective_budget == 200
    assert result.budget_metadata.memory_used_tokens > 0
    assert result.budget_metadata.knowledge_used_tokens > 0
    assert any(
        decision.source_type == "memory" and decision.included
        for decision in result.budget_metadata.decisions
    )
    assert any(
        decision.source_type == "knowledge" and decision.included
        for decision in result.budget_metadata.decisions
    )


async def test_empty_knowledge_results_are_omitted(monkeypatch):
    from fleetent import long_term_ctx

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
            },
        ),
    )
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    knowledge_search = AsyncMock(return_value=[])
    long_term_ctx.set_knowledge_provider(knowledge_search)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="deployment",
        agent_id="agent-1",
        available_tokens=200,
    )

    knowledge_search.assert_awaited_once_with(
        Principal(user_id="user-1", tenant_id="tenant-a"),
        "deployment",
        ["global"],
        10,
        None,
    )
    assert result.text == ""
    assert result.sources == []
    assert "[Knowledge" not in result.text


async def test_memory_and_knowledge_results_are_included_with_sources(monkeypatch):
    from fleetent import long_term_ctx

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
            },
        ),
    )
    memory = _mem_result("User is deploying on-prem")
    knowledge = SimpleNamespace(
        id="doc-1",
        content="Fleetent supports self-hosted deployment.",
        score=0.8,
        metadata={"title": "Deployment guide"},
    )
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[memory]))
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[knowledge]))

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="deployment",
        agent_id="agent-1",
        available_tokens=300,
    )

    assert "[Long-term memory" in result.text
    assert "User is deploying on-prem" in result.text
    assert "[Knowledge" in result.text
    assert "Fleetent supports self-hosted deployment." in result.text
    assert [source.source_type for source in result.sources] == ["memory", "knowledge"]
    assert [source.source_id for source in result.sources] == ["mem-1", "doc-1"]


async def test_budget_pressure_keeps_memory_and_omits_low_priority_knowledge(monkeypatch):
    from fleetent import long_term_ctx

    _publish_agent(
        monkeypatch,
        AgentFile(
            name="agent-1",
            version=1,
            models=default_models(),
            knowledge={
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
            },
        ),
    )
    memory = _mem_result("User prefers concise answers.")
    knowledge = SimpleNamespace(
        id="doc-1",
        content="Knowledge chunk " + ("too large " * 30),
        score=0.95,
        metadata={"title": "Large doc"},
    )
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[memory]))
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[knowledge]))

    # The budget is a char-count proxy: the memory section ("[Long-term memory — …]"
    # header + one fact line) renders to ~91 chars, while the large knowledge chunk
    # is ~318. Pick a budget that admits memory but excludes the low-priority
    # knowledge. (Tune this if the section header wording changes its length.)
    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="answer style",
        agent_id="agent-1",
        available_tokens=100,
    )

    assert len(result.text) <= 100
    assert "User prefers concise answers." in result.text
    assert "Knowledge chunk" not in result.text
    assert [source.source_id for source in result.sources] == ["mem-1"]
