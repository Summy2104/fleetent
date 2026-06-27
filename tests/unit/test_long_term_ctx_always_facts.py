"""Unit tests: build_context injects always-scope facts unconditionally."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fleetent.memory.facts_models import Fact
from fleetent.long_term_ctx import BuiltContext


def _always_fact(fid: str, relation: str = "response_style", object: str = "加 xin 在句末") -> Fact:
    now = datetime.now(UTC).replace(microsecond=0)
    return Fact(
        fact_id=fid,
        user_id="u1",
        subject="agent",
        relation=relation,
        object=object,
        cardinality="single",
        status="active",
        access_count=0,
        first_accessed_at=None,
        last_accessed_at=None,
        expires_at=None,
        valid_until=None,
        created_at=now,
        updated_at=now,
        source_turn=None,
        statement=f"用户希望助手{object}",
        scope="always",
    )


async def test_always_facts_injected_unconditionally(monkeypatch) -> None:
    """Always facts appear in context even when vector search returns nothing."""
    import fleetent.long_term_ctx as ltc

    always = [_always_fact("f1")]

    monkeypatch.setattr(ltc, "_list_always_facts", lambda uid: always)

    async def _no_situational(uid, q, limit):
        return []

    async def _no_knowledge(*a, **k):
        return []

    async def _no_agent_memory(*a, **k):
        return []

    monkeypatch.setattr(ltc, "_search_facts_situational", _no_situational)
    monkeypatch.setattr(ltc, "_search_knowledge", _no_knowledge)
    monkeypatch.setattr(ltc, "_search_agent_memory", _no_agent_memory)

    ctx = await ltc.build_context("u1", "帮我写代码", "agent1", 4096)

    assert "[Behavioral directives" in ctx.text
    assert "加 xin 在句末" in ctx.text


async def test_always_facts_section_before_memory_section(monkeypatch) -> None:
    """Behavioral directives section appears before Long-term memory section."""
    import fleetent.long_term_ctx as ltc

    always = [_always_fact("f1")]
    situational_result = _make_search_result("f2", "has_skill", "Python")

    monkeypatch.setattr(ltc, "_list_always_facts", lambda uid: always)

    async def _with_situational(uid, q, limit):
        return [situational_result]

    async def _no_knowledge(*a, **k):
        return []

    async def _no_agent_memory(*a, **k):
        return []

    monkeypatch.setattr(ltc, "_search_facts_situational", _with_situational)
    monkeypatch.setattr(ltc, "_search_knowledge", _no_knowledge)
    monkeypatch.setattr(ltc, "_search_agent_memory", _no_agent_memory)

    ctx = await ltc.build_context("u1", "你会 Python 吗", "agent1", 4096)

    directives_pos = ctx.text.find("[Behavioral directives")
    memory_pos = ctx.text.find("[Long-term memory")
    assert directives_pos != -1
    assert memory_pos != -1
    assert directives_pos < memory_pos


async def test_no_always_facts_omits_directives_section(monkeypatch) -> None:
    """No always facts → no [Behavioral directives] section in output."""
    import fleetent.long_term_ctx as ltc

    monkeypatch.setattr(ltc, "_list_always_facts", lambda uid: [])

    async def _empty(*a, **k):
        return []

    monkeypatch.setattr(ltc, "_search_facts_situational", _empty)
    monkeypatch.setattr(ltc, "_search_knowledge", _empty)
    monkeypatch.setattr(ltc, "_search_agent_memory", _empty)

    ctx = await ltc.build_context("u1", "hello", "agent1", 4096)

    assert "[Behavioral directives" not in ctx.text


async def test_always_facts_included_in_sources(monkeypatch) -> None:
    """Always facts contribute to BuiltContext.sources with source_type='memory'."""
    import fleetent.long_term_ctx as ltc

    always = [_always_fact("f1")]

    monkeypatch.setattr(ltc, "_list_always_facts", lambda uid: always)

    async def _empty(*a, **k):
        return []

    monkeypatch.setattr(ltc, "_search_facts_situational", _empty)
    monkeypatch.setattr(ltc, "_search_knowledge", _empty)
    monkeypatch.setattr(ltc, "_search_agent_memory", _empty)

    ctx = await ltc.build_context("u1", "hello", "agent1", 4096)

    memory_sources = [s for s in ctx.sources if s.source_type == "memory"]
    assert any(s.source_id == "f1" for s in memory_sources)


# ── helpers ───────────────────────────────────────────────────────────────────


def _never_called(*a, **k):
    raise AssertionError("should not be called")


def _make_search_result(fid: str, relation: str, obj: str):
    from fleetent.memory.facts_models import SearchResult

    now = datetime.now(UTC).replace(microsecond=0)
    fact = Fact(
        fact_id=fid,
        user_id="u1",
        subject="user",
        relation=relation,
        object=obj,
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
        scope="situational",
    )
    return SearchResult(fact=fact, score=0.8)
