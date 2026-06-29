from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fleetent import agent_config
from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models
from fleetent.config import LongTermContextSettings
from fleetent.memory.facts_models import Fact, SearchResult

# Rendered memory line makes the subject explicit so the LLM never mistakes a
# user fact for its own; with subject="user" and relation="has_preference" the
# fixed prefix below precedes every object text.
_MEM_LINE_PREFIX = "- The user's has_preference: "


def _mem_result(object_text: str, fact_id: str = "mem-1", score: float = 0.9) -> SearchResult:
    now = datetime(2026, 6, 2, tzinfo=UTC)
    return SearchResult(
        fact=Fact(
            fact_id=fact_id,
            user_id="user-1",
            subject="user",
            relation="has_preference",
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
        ),
        score=score,
    )


def _memory(memory_id: str, content: str) -> SearchResult:
    return _mem_result(content, fact_id=memory_id)


def _knowledge(source_id: str, content: str, score: float = 1.0) -> SimpleNamespace:
    return SimpleNamespace(
        id=source_id,
        content=content,
        score=score,
        metadata={"title": source_id},
    )


def _ltc(**long_term_ctx_kwargs: object) -> LongTermContextSettings:
    return LongTermContextSettings(**long_term_ctx_kwargs)


@pytest.fixture(autouse=True)
def _publish_kb_enabled_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent_config,
        "_index",
        AgentConfigIndex(
            agents={
                "agent-1": AgentFile(
                    name="agent-1",
                    version=1,
                    models=default_models(),
                    knowledge={
                        "enabled": True,
                        "bindings": [{"tenant_id": "tenant-a", "kb_id": "global"}],
                    },
                )
            },
            default="agent-1",
        ),
    )


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
        agent_memory_max_tokens=64,
        memory_top_k=3,
        knowledge_top_k=2,
        agent_memory_top_k=3,
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

    memory = _mem_result("Use concise answers.")
    monkeypatch.setattr(
        long_term_ctx, "_ltc_config", lambda: LongTermContextSettings(max_tokens=35)
    )
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[memory]))
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
            memory_max_tokens=50,
            knowledge_max_tokens=45,
            memory_top_k=10,
            knowledge_top_k=10,
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search_facts",
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
        "search_facts",
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
            max_tokens=90,
            memory_max_tokens=500,
            knowledge_max_tokens=500,
            memory_top_k=10,
            knowledge_top_k=10,
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search_facts",
        AsyncMock(return_value=[_memory("mem-1", "Short memory.")]),
    )
    long_term_ctx.set_knowledge_provider(
        AsyncMock(return_value=[_knowledge("doc-1", "Knowledge text that cannot fit.")])
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="preferences",
        agent_id="agent-1",
        available_tokens=90,
    )

    assert len(result.text) <= 90
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
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
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
        "search_facts",
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
            max_tokens=80,
            memory_max_tokens=500,
            knowledge_max_tokens=500,
            memory_top_k=10,
            knowledge_top_k=10,
            conflict_preference="auto",
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search_facts",
        AsyncMock(return_value=[_memory("mem-1", "Old.")]),
    )
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[_knowledge("doc-1", "New.")]))

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="remember my preference",
        agent_id="agent-1",
        available_tokens=80,
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
        "search_facts",
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
        "search_facts",
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
    assert decision.token_estimate == len(_MEM_LINE_PREFIX + "Short memory.")
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
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
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


# Task 3.1: LongTermContextSettings agent_memory fields + 3-way conflict_preference


def test_long_term_context_settings_has_agent_memory_budget_fields():
    settings = LongTermContextSettings(
        agent_memory_max_tokens=512,
        agent_memory_top_k=5,
    )

    assert settings.agent_memory_max_tokens == 512
    assert settings.agent_memory_top_k == 5


def test_long_term_context_settings_agent_memory_fields_have_defaults():
    settings = LongTermContextSettings()

    assert isinstance(settings.agent_memory_max_tokens, int)
    assert settings.agent_memory_max_tokens > 0
    assert isinstance(settings.agent_memory_top_k, int)
    assert settings.agent_memory_top_k > 0


def test_conflict_preference_accepts_agent_memory():
    settings = LongTermContextSettings(conflict_preference="agent_memory")

    assert settings.conflict_preference == "agent_memory"


def test_conflict_preference_all_three_party_values_accepted():
    for value in ("memory", "knowledge", "agent_memory"):
        s = LongTermContextSettings(conflict_preference=value)
        assert s.conflict_preference == value


# Task 3.2: build_context calls search_agent_memory; hits produce source_type="agent_memory"


def _agent_memory_item(item_id: str, content: str) -> object:
    from datetime import UTC, datetime

    from fleetent.memory.models import AgentMemoryItem

    now = datetime(2026, 6, 24, tzinfo=UTC)
    return AgentMemoryItem(
        id=item_id,
        type="preference",
        content=content,
        status="active",
        source="manual",
        source_ref=None,
        created_by="user-1",
        created_at=now,
        updated_at=now,
    )


async def test_build_context_agent_memory_hits_produce_agent_memory_source_type(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(long_term_ctx, "_ltc_config", lambda: LongTermContextSettings())
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[]))
    monkeypatch.setattr(
        long_term_ctx.agent_memory,
        "search_agent_memory",
        AsyncMock(return_value=[_agent_memory_item("am-1", "Use concise bullet points.")]),
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="style preference",
        agent_id="agent-1",
        available_tokens=500,
    )

    assert any(s.source_type == "agent_memory" for s in result.sources)
    assert any(s.source_id == "am-1" for s in result.sources)


async def test_build_context_search_agent_memory_called_without_user_id(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(long_term_ctx, "_ltc_config", lambda: LongTermContextSettings())
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[]))
    search_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(long_term_ctx.agent_memory, "search_agent_memory", search_mock)

    await long_term_ctx.build_context(
        user_id="user-1",
        query="style preference",
        agent_id="agent-1",
        available_tokens=500,
    )

    search_mock.assert_awaited_once()
    call_kwargs = search_mock.call_args
    # must NOT pass user_id — agent_memory is scoped to the agent, not per-user
    assert "user_id" not in (call_kwargs.kwargs if call_kwargs.kwargs else {})


async def test_build_context_empty_agent_memory_omits_agent_memory_section(monkeypatch):
    from fleetent import long_term_ctx

    monkeypatch.setattr(long_term_ctx, "_ltc_config", lambda: LongTermContextSettings())
    monkeypatch.setattr(long_term_ctx.memory, "search_facts", AsyncMock(return_value=[]))
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[]))
    monkeypatch.setattr(
        long_term_ctx.agent_memory,
        "search_agent_memory",
        AsyncMock(return_value=[]),
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="style preference",
        agent_id="agent-1",
        available_tokens=500,
    )

    assert "[Agent memory]" not in result.text
    assert not any(s.source_type == "agent_memory" for s in result.sources)


# Task 3.4: 三源预算互不挤占 + conflict_preference 三方优先级


async def test_agent_memory_budget_does_not_crowd_out_memory_or_knowledge(monkeypatch):
    """A tight agent_memory_max_tokens budget must not reduce memory or knowledge allocations."""
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: LongTermContextSettings(
            max_tokens=500,
            memory_max_tokens=200,
            knowledge_max_tokens=200,
            agent_memory_max_tokens=20,  # very tight; must not spill into memory/knowledge budgets
            memory_top_k=5,
            knowledge_top_k=5,
            agent_memory_top_k=5,
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search_facts",
        AsyncMock(
            return_value=[
                _memory("mem-1", "Memory item one."),
                _memory("mem-2", "Memory item two."),
            ]
        ),
    )
    long_term_ctx.set_knowledge_provider(
        AsyncMock(return_value=[_knowledge("doc-1", "Knowledge doc one.")])
    )
    monkeypatch.setattr(
        long_term_ctx.agent_memory,
        "search_agent_memory",
        AsyncMock(
            return_value=[_agent_memory_item("am-1", "x" * 30)]
        ),  # exceeds agent_memory budget
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="style preferences",
        agent_id="agent-1",
        available_tokens=500,
    )

    included_types = {s.source_type for s in result.sources}
    # memory and knowledge should still be included despite agent_memory budget overflow
    assert "memory" in included_types
    assert "knowledge" in included_types
    # agent_memory item was too large for its own budget
    assert "am-1" not in {s.source_id for s in result.sources}


async def test_conflict_preference_agent_memory_first_in_ordering(monkeypatch):
    """conflict_preference='agent_memory' places agent_memory candidates first."""
    from fleetent import long_term_ctx

    monkeypatch.setattr(
        long_term_ctx,
        "_ltc_config",
        lambda: LongTermContextSettings(
            max_tokens=60,  # tight: only first source wins
            memory_max_tokens=60,
            knowledge_max_tokens=60,
            agent_memory_max_tokens=60,
            memory_top_k=5,
            knowledge_top_k=5,
            agent_memory_top_k=5,
            conflict_preference="agent_memory",
        ),
    )
    monkeypatch.setattr(
        long_term_ctx.memory,
        "search_facts",
        AsyncMock(return_value=[_memory("mem-1", "Some user memory.")]),
    )
    long_term_ctx.set_knowledge_provider(AsyncMock(return_value=[]))
    monkeypatch.setattr(
        long_term_ctx.agent_memory,
        "search_agent_memory",
        AsyncMock(return_value=[_agent_memory_item("am-1", "Agent-scoped preference.")]),
    )

    result = await long_term_ctx.build_context(
        user_id="user-1",
        query="preference",
        agent_id="agent-1",
        available_tokens=60,
    )

    assert result.sources, "expected at least one source"
    assert result.sources[0].source_type == "agent_memory", (
        f"expected agent_memory first, got {result.sources[0].source_type}"
    )
