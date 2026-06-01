from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fleetent.config import KnowledgeBaseSettings, Settings
from fleetent.intelligence.knowledge_base import KnowledgeChunk
from fleetent.memory_layer import MemoryItem


async def test_public_api_is_importable():
    from fleetent.intelligence.long_term_ctx import BuiltContext, ContextSource, build_context

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
    from fleetent.intelligence import long_term_ctx

    memory_search = AsyncMock()
    knowledge_search = AsyncMock()
    monkeypatch.setattr(long_term_ctx.memory_layer, "search", memory_search)
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
    from fleetent.intelligence import long_term_ctx

    memory_search = AsyncMock(return_value=[])
    monkeypatch.setattr(long_term_ctx.memory_layer, "search", memory_search)
    long_term_ctx.set_knowledge_provider(None)

    await long_term_ctx.build_context(
        user_id="user-1",
        query="python debugging",
        agent_id="agent-1",
        available_tokens=200,
    )

    memory_search.assert_awaited_once_with("user-1", "python debugging", limit=10)


async def test_memory_results_are_formatted_with_memory_source_summary(monkeypatch):
    from fleetent.intelligence import long_term_ctx

    now = datetime(2026, 5, 31, tzinfo=UTC)
    memory = MemoryItem(
        id="mem-1",
        user_id="user-1",
        type="preferences",
        content="User prefers Python for backend services",
        created_at=now,
        updated_at=now,
        expires_at=None,
    )
    monkeypatch.setattr(long_term_ctx.memory_layer, "search", AsyncMock(return_value=[memory]))
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
    assert result.sources[0].metadata == {"type": "preferences"}


async def test_missing_knowledge_provider_does_not_block_memory_context(monkeypatch):
    from fleetent.intelligence import long_term_ctx

    now = datetime(2026, 5, 31, tzinfo=UTC)
    memory = MemoryItem(
        id="mem-1",
        user_id="user-1",
        type="identity",
        content="User works on fleetent",
        created_at=now,
        updated_at=now,
        expires_at=None,
    )
    monkeypatch.setattr(long_term_ctx.memory_layer, "search", AsyncMock(return_value=[memory]))
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
    from fleetent.intelligence import long_term_ctx

    settings = Settings(
        anthropic_api_key="test-key",
        knowledge_base=KnowledgeBaseSettings(
            enabled=True,
            default_tenant_id="tenant-a",
            default_kb_id="global",
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
    monkeypatch.setattr(long_term_ctx.memory_layer, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(long_term_ctx, "Settings", lambda anthropic_api_key="": settings)
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
    from fleetent.intelligence import long_term_ctx

    settings = Settings(
        anthropic_api_key="test-key",
        knowledge_base=KnowledgeBaseSettings(enabled=False),
    )
    knowledge_search = AsyncMock(return_value=[])
    monkeypatch.setattr(long_term_ctx.memory_layer, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(long_term_ctx, "Settings", lambda anthropic_api_key="": settings)
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


async def test_empty_knowledge_results_are_omitted(monkeypatch):
    from fleetent.intelligence import long_term_ctx

    monkeypatch.setattr(long_term_ctx.memory_layer, "search", AsyncMock(return_value=[]))
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
    from fleetent.intelligence import long_term_ctx

    now = datetime(2026, 5, 31, tzinfo=UTC)
    memory = MemoryItem(
        id="mem-1",
        user_id="user-1",
        type="context",
        content="User is deploying on-prem",
        created_at=now,
        updated_at=now,
        expires_at=None,
    )
    knowledge = SimpleNamespace(
        id="doc-1",
        content="Fleetent supports self-hosted deployment.",
        score=0.8,
        metadata={"title": "Deployment guide"},
    )
    monkeypatch.setattr(long_term_ctx.memory_layer, "search", AsyncMock(return_value=[memory]))
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
    from fleetent.intelligence import long_term_ctx

    now = datetime(2026, 5, 31, tzinfo=UTC)
    memory = MemoryItem(
        id="mem-1",
        user_id="user-1",
        type="identity",
        content="User prefers concise answers.",
        created_at=now,
        updated_at=now,
        expires_at=None,
    )
    knowledge = SimpleNamespace(
        id="doc-1",
        content="Knowledge chunk " + ("too large " * 30),
        score=0.95,
        metadata={"title": "Large doc"},
    )
    monkeypatch.setattr(long_term_ctx.memory_layer, "search", AsyncMock(return_value=[memory]))
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[knowledge]))

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="answer style",
        agent_id="agent-1",
        available_tokens=70,
    )

    assert len(result.text) <= 70
    assert "User prefers concise answers." in result.text
    assert "Knowledge chunk" not in result.text
    assert [source.source_id for source in result.sources] == ["mem-1"]
