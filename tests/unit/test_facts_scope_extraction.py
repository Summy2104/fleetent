"""Unit tests: facts extraction outputs correct scope field."""

from __future__ import annotations

import pytest


async def test_behavioral_directive_extracted_as_always(monkeypatch) -> None:
    """LLM output with scope='always' → RawFact.scope='always'."""
    from fleetent.memory import facts_pipeline

    llm_output = '[{"subject": "agent", "relation": "response_style", "object": "加 xin 在句末", "temporal": "none", "statement": "用户希望助手每次回复后加 xin", "scope": "always"}]'

    async def _fake_create(**kwargs):
        class _Msg:
            content = llm_output

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()

    class _FakeLLM:
        _fleetent_model = "test"

        class chat:
            class completions:
                create = staticmethod(_fake_create)

    results = await facts_pipeline.extract_facts("以后回复我要加 xin", _FakeLLM())
    assert len(results) == 1
    assert results[0].scope == "always"


async def test_factual_preference_extracted_as_situational(monkeypatch) -> None:
    """LLM output with scope='situational' → RawFact.scope='situational'."""
    from fleetent.memory import facts_pipeline

    llm_output = '[{"subject": "user", "relation": "prefers_language", "object": "TypeScript", "temporal": "none", "statement": "用户喜欢 TypeScript", "scope": "situational"}]'

    async def _fake_create(**kwargs):
        class _Msg:
            content = llm_output

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()

    class _FakeLLM:
        _fleetent_model = "test"

        class chat:
            class completions:
                create = staticmethod(_fake_create)

    results = await facts_pipeline.extract_facts("我喜欢 TypeScript", _FakeLLM())
    assert len(results) == 1
    assert results[0].scope == "situational"


async def test_missing_scope_defaults_to_situational(monkeypatch) -> None:
    """LLM output without scope field → defaults to 'situational'."""
    from fleetent.memory import facts_pipeline

    llm_output = '[{"subject": "user", "relation": "name", "object": "Xin", "temporal": "none", "statement": "用户的名字是 Xin"}]'

    async def _fake_create(**kwargs):
        class _Msg:
            content = llm_output

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()

    class _FakeLLM:
        _fleetent_model = "test"

        class chat:
            class completions:
                create = staticmethod(_fake_create)

    results = await facts_pipeline.extract_facts("我叫 Xin", _FakeLLM())
    assert len(results) == 1
    assert results[0].scope == "situational"
