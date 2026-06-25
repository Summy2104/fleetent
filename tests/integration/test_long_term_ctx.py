from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fleetent import agent_config
from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models
from fleetent.config import LongTermContextSettings
from fleetent.knowledge_base import KnowledgeChunk
from fleetent.memory.facts_models import Fact, SearchResult


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

    assert "[Long-term memory]" in result.text
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
    assert "[Knowledge]" not in result.text


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
    assert "[Knowledge]" in result.text
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
    monkeypatch.setattr(
        long_term_ctx.memory, "search_facts", AsyncMock(return_value=[memory_item])
    )
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

    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    knowledge_search = AsyncMock(return_value=[])
    long_term_ctx.set_knowledge_provider(knowledge_search)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="deployment",
        agent_id="agent-1",
        available_tokens=200,
    )

    knowledge_search.assert_awaited_once_with("user-1", "deployment", "agent-1", 10)
    assert result.text == ""
    assert result.sources == []
    assert "[Knowledge]" not in result.text


async def test_memory_and_knowledge_results_are_included_with_sources(monkeypatch):
    from fleetent import long_term_ctx

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

    assert "[Long-term memory]" in result.text
    assert "User is deploying on-prem" in result.text
    assert "[Knowledge]" in result.text
    assert "Fleetent supports self-hosted deployment." in result.text
    assert [source.source_type for source in result.sources] == ["memory", "knowledge"]
    assert [source.source_id for source in result.sources] == ["mem-1", "doc-1"]


async def test_budget_pressure_keeps_memory_and_omits_low_priority_knowledge(monkeypatch):
    from fleetent import long_term_ctx

    memory = _mem_result("User prefers concise answers.")
    knowledge = SimpleNamespace(
        id="doc-1",
        content="Knowledge chunk " + ("too large " * 30),
        score=0.95,
        metadata={"title": "Large doc"},
    )
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[memory]))
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[knowledge]))

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="answer style",
        agent_id="agent-1",
        available_tokens=78,
    )

    assert len(result.text) <= 78
    assert "User prefers concise answers." in result.text
    assert "Knowledge chunk" not in result.text
    assert [source.source_id for source in result.sources] == ["mem-1"]
