from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fleetent.config import LongTermContextSettings
from fleetent.memory import MemoryItem


def _memory(memory_id: str, content: str) -> MemoryItem:
    now = datetime(2026, 6, 2, tzinfo=UTC)
    return MemoryItem(
        id=memory_id,
        user_id="user-1",
        type="preference",
        content=content,
        created_at=now,
        updated_at=now,
        expires_at=None,
    )


def _knowledge(source_id: str, content: str, score: float = 1.0) -> SimpleNamespace:
    return SimpleNamespace(
        id=source_id,
        content=content,
        score=score,
        metadata={"title": source_id},
    )


def _ltc(**long_term_ctx_kwargs: object) -> LongTermContextSettings:
    return LongTermContextSettings(**long_term_ctx_kwargs)


def test_budget_policy_public_api_is_importable():
    from fleetent.long_term_ctx import (
        BudgetDecision,
        BudgetMetadata,
        BudgetPolicy,
    )

    policy = BudgetPolicy(
        max_tokens=200,
        memory_max_tokens=120,
        knowledge_max_tokens=80,
        memory_top_k=3,
        knowledge_top_k=2,
        conflict_preference="auto",
    )
    decision = BudgetDecision(
        source_type="memory",
        source_id="mem-1",
        token_estimate=42,
        reason="included",
        included=True,
    )
    metadata = BudgetMetadata(
        effective_budget=200,
        memory_used_tokens=42,
        knowledge_used_tokens=0,
        decisions=[decision],
    )

    assert policy.memory_top_k == 3
    assert metadata.decisions == [decision]


def test_built_context_exposes_budget_metadata_without_breaking_existing_callers():
    from fleetent.long_term_ctx import BudgetMetadata, BuiltContext, ContextSource

    source = ContextSource(
        source_type="memory",
        source_id="mem-1",
        score=1.0,
        metadata={"type": "preference"},
    )

    context = BuiltContext(text="remembered context", sources=[source])

    assert context.text == "remembered context"
    assert context.sources == [source]
    assert isinstance(context.budget_metadata, BudgetMetadata)
    assert context.budget_metadata.effective_budget == 0
    assert context.budget_metadata.decisions == []


async def test_effective_budget_uses_available_tokens_and_configured_maximum(monkeypatch):
    from fleetent import long_term_ctx

    now = datetime(2026, 6, 2, tzinfo=UTC)
    memory = MemoryItem(
        id="mem-1",
        user_id="user-1",
        type="preference",
        content="Use concise answers.",
        created_at=now,
        updated_at=now,
        expires_at=None,
    )
    monkeypatch.setattr(
        long_term_ctx, "_ltc_config", lambda: LongTermContextSettings(max_tokens=35)
    )
    monkeypatch.setattr(long_term_ctx.memory, "search", AsyncMock(return_value=[memory]))
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[]))

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="answer style",
        agent_id="agent-1",
        available_tokens=80,
    )

    assert result.budget_metadata.effective_budget == 35
    assert len(result.text) <= 35


async def test_zero_available_tokens_short_circuits_with_metadata(monkeypatch):
    from fleetent import long_term_ctx

    memory_search = AsyncMock(return_value=[])
    knowledge_search = AsyncMock(return_value=[])
    monkeypatch.setattr(long_term_ctx.memory, "search", memory_search)
    long_term_ctx.set_knowledge_provider(knowledge_search)

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="python",
        agent_id="agent-1",
        available_tokens=0,
    )

    assert result.text == ""
    assert result.sources == []
    assert result.budget_metadata.effective_budget == 0
    assert result.budget_metadata.decisions[0].reason == "zero_available_tokens"
    memory_search.assert_not_awaited()
    knowledge_search.assert_not_awaited()


def test_long_term_context_settings_include_source_budget_policy_fields():
    settings = LongTermContextSettings(
        max_tokens=100,
        memory_max_tokens=60,
        knowledge_max_tokens=40,
        memory_top_k=3,
        knowledge_top_k=2,
        conflict_preference="knowledge",
    )

    assert settings.memory_max_tokens == 60
    assert settings.knowledge_max_tokens == 40
    assert settings.memory_top_k == 3
    assert settings.knowledge_top_k == 2
    assert settings.conflict_preference == "knowledge"


async def test_source_token_budgets_are_applied_per_source_type(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: _ltc(
            max_tokens=500,
            memory_max_tokens=30,
            knowledge_max_tokens=45,
            memory_top_k=10,
            knowledge_top_k=10,
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search",
        AsyncMock(
            return_value=[
                _memory("mem-short", "Short memory."),
                _memory("mem-long", "This memory is too large for its source budget."),
            ]
        ),
    )
    long_term_ctx.set_knowledge_provider(
        AsyncMock(
            return_value=[
                _knowledge("doc-short", "Short knowledge."),
                _knowledge("doc-long", "This knowledge entry is too large for the KB budget."),
            ]
        )
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="preferences",
        agent_id="agent-1",
        available_tokens=500,
    )

    assert [source.source_id for source in result.sources] == ["mem-short", "doc-short"]
    excluded = {
        decision.source_id: decision.reason
        for decision in result.budget_metadata.decisions
        if not decision.included
    }
    assert excluded["mem-long"] == "source_budget_exceeded"
    assert excluded["doc-long"] == "source_budget_exceeded"


async def test_source_top_k_limits_are_applied_per_source_type(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: _ltc(
            max_tokens=500,
            memory_max_tokens=500,
            knowledge_max_tokens=500,
            memory_top_k=1,
            knowledge_top_k=1,
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search",
        AsyncMock(return_value=[_memory("mem-a", "A memory."), _memory("mem-b", "B memory.")]),
    )
    long_term_ctx.set_knowledge_provider(
        AsyncMock(return_value=[_knowledge("doc-a", "A doc."), _knowledge("doc-b", "B doc.")])
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="preferences",
        agent_id="agent-1",
        available_tokens=500,
    )

    assert [source.source_id for source in result.sources] == ["mem-a", "doc-a"]
    excluded = {
        decision.source_id: decision.reason
        for decision in result.budget_metadata.decisions
        if not decision.included
    }
    assert excluded["mem-b"] == "source_top_k_exceeded"
    assert excluded["doc-b"] == "source_top_k_exceeded"


async def test_total_budget_excludes_candidates_that_do_not_fit(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: _ltc(
            max_tokens=55,
            memory_max_tokens=500,
            knowledge_max_tokens=500,
            memory_top_k=10,
            knowledge_top_k=10,
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search",
        AsyncMock(return_value=[_memory("mem-1", "Short memory.")]),
    )
    long_term_ctx.set_knowledge_provider(
        AsyncMock(return_value=[_knowledge("doc-1", "Knowledge text that cannot fit.")])
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="preferences",
        agent_id="agent-1",
        available_tokens=55,
    )

    assert len(result.text) <= 55
    assert [source.source_id for source in result.sources] == ["mem-1"]
    assert any(
        decision.source_id == "doc-1" and decision.reason == "total_budget_exceeded"
        for decision in result.budget_metadata.decisions
    )


async def test_equal_score_candidates_use_stable_source_id_tie_breaker(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: _ltc(
            max_tokens=500,
            memory_max_tokens=500,
            knowledge_max_tokens=500,
            memory_top_k=10,
            knowledge_top_k=10,
        ),
    )
    monkeypatch.setattr(long_term_ctx.memory, "search", AsyncMock(return_value=[]))
    long_term_ctx.set_knowledge_provider(
        AsyncMock(
            return_value=[
                _knowledge("doc-b", "B doc.", score=0.8),
                _knowledge("doc-a", "A doc.", score=0.8),
            ]
        )
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="reference docs",
        agent_id="agent-1",
        available_tokens=500,
    )

    assert [source.source_id for source in result.sources] == ["doc-a", "doc-b"]


async def test_factual_queries_prefer_knowledge_when_budget_forces_a_choice(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: _ltc(
            max_tokens=40,
            memory_max_tokens=500,
            knowledge_max_tokens=500,
            memory_top_k=10,
            knowledge_top_k=10,
            conflict_preference="auto",
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search",
        AsyncMock(return_value=[_memory("mem-1", "Old.")]),
    )
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[_knowledge("doc-1", "New.")]))

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="what does the policy say",
        agent_id="agent-1",
        available_tokens=40,
    )

    assert [source.source_id for source in result.sources] == ["doc-1"]


async def test_personal_history_queries_prefer_memory_when_budget_forces_a_choice(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: _ltc(
            max_tokens=40,
            memory_max_tokens=500,
            knowledge_max_tokens=500,
            memory_top_k=10,
            knowledge_top_k=10,
            conflict_preference="auto",
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search",
        AsyncMock(return_value=[_memory("mem-1", "Old.")]),
    )
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[_knowledge("doc-1", "New.")]))

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="remember my preference",
        agent_id="agent-1",
        available_tokens=40,
    )

    assert [source.source_id for source in result.sources] == ["mem-1"]


async def test_explicit_conflict_preference_overrides_auto_intent(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: _ltc(
            max_tokens=40,
            memory_max_tokens=500,
            knowledge_max_tokens=500,
            memory_top_k=10,
            knowledge_top_k=10,
            conflict_preference="knowledge",
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search",
        AsyncMock(return_value=[_memory("mem-1", "Old.")]),
    )
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[_knowledge("doc-1", "New.")]))

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="remember my preference",
        agent_id="agent-1",
        available_tokens=40,
    )

    assert [source.source_id for source in result.sources] == ["doc-1"]


async def test_included_sources_have_budget_decision_metadata(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: _ltc(
            max_tokens=500,
            memory_max_tokens=500,
            knowledge_max_tokens=500,
            memory_top_k=10,
            knowledge_top_k=10,
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search",
        AsyncMock(return_value=[_memory("mem-1", "Short memory.")]),
    )
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[]))

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="remember my preference",
        agent_id="agent-1",
        available_tokens=500,
    )

    decision = result.budget_metadata.decisions[0]
    assert decision.included is True
    assert decision.source_type == "memory"
    assert decision.source_id == "mem-1"
    assert decision.token_estimate == len("- Short memory.")
    assert decision.reason == "included"


async def test_below_relevance_threshold_sources_are_excluded_with_reason(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: _ltc(
            max_tokens=500,
            memory_max_tokens=500,
            knowledge_max_tokens=500,
            memory_top_k=10,
            knowledge_top_k=10,
        ),
    )
    monkeypatch.setattr(long_term_ctx.memory, "search", AsyncMock(return_value=[]))
    long_term_ctx.set_knowledge_provider(
        AsyncMock(return_value=[_knowledge("doc-low", "Unrelated.", score=0.0)])
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="reference docs",
        agent_id="agent-1",
        available_tokens=500,
    )

    assert result.sources == []
    assert result.budget_metadata.decisions[0].source_id == "doc-low"
    assert result.budget_metadata.decisions[0].reason == "below_relevance_threshold"
