"""Unit tests: extract_facts parses LLM output into RawFact list."""

from __future__ import annotations

import json

import pytest


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content
        self.chat = self
        self.completions = self
        self.last_messages: list[dict] = []

    async def create(self, **kwargs):
        self.last_messages = kwargs.get("messages", [])

        class _Msg:
            def __init__(self, content: str) -> None:
                self.content = content

        class _Choice:
            def __init__(self, content: str) -> None:
                self.message = _Msg(content)

        class _Resp:
            def __init__(self, content: str) -> None:
                self.choices = [_Choice(content)]

        return _Resp(self._content)


async def test_extract_single_fact() -> None:
    from fleetent.memory import facts_pipeline

    payload = json.dumps(
        [{"subject": "user", "relation": "is_role", "object": "Python developer", "temporal": "none"}]
    )
    facts = await facts_pipeline.extract_facts(
        turn_content="I am a Python developer", llm_client=_FakeLLM(payload)
    )
    assert len(facts) == 1
    assert facts[0].relation == "is_role"
    assert facts[0].object == "Python developer"
    assert facts[0].temporal == "none"


async def test_extract_fact_with_temporal_intent() -> None:
    from fleetent.memory import facts_pipeline

    # The LLM emits a temporal-intent LABEL (not a date); code computes the expiry.
    payload = json.dumps(
        [
            {
                "subject": "user",
                "relation": "ate",
                "object": "pancakes",
                "temporal": "today",
            }
        ]
    )
    facts = await facts_pipeline.extract_facts(
        turn_content="I ate pancakes this morning", llm_client=_FakeLLM(payload)
    )
    assert facts[0].temporal == "today"


async def test_extract_missing_temporal_defaults_none() -> None:
    from fleetent.memory import facts_pipeline

    # No temporal key → defaults to "none" (no time-based expiry).
    payload = json.dumps(
        [{"subject": "user", "relation": "is_role", "object": "dev"}]
    )
    facts = await facts_pipeline.extract_facts("...", llm_client=_FakeLLM(payload))
    assert facts[0].temporal == "none"


async def test_extract_empty_when_no_facts() -> None:
    from fleetent.memory import facts_pipeline

    facts = await facts_pipeline.extract_facts(
        turn_content="What's the weather?", llm_client=_FakeLLM("[]")
    )
    assert facts == []


async def test_extract_skips_malformed_entries() -> None:
    from fleetent.memory import facts_pipeline

    payload = json.dumps(
        [
            {"subject": "user", "relation": "is_role", "object": "dev", "valid_until": None},
            {"relation": "missing_subject_and_object"},  # malformed
            {"subject": "user", "object": "no relation", "valid_until": None},  # malformed
        ]
    )
    facts = await facts_pipeline.extract_facts(
        turn_content="...", llm_client=_FakeLLM(payload)
    )
    assert len(facts) == 1
    assert facts[0].object == "dev"


async def test_extract_handles_json_fence() -> None:
    from fleetent.memory import facts_pipeline

    payload = (
        "```json\n"
        + json.dumps(
            [{"subject": "user", "relation": "has_skill", "object": "Rust", "valid_until": None}]
        )
        + "\n```"
    )
    facts = await facts_pipeline.extract_facts(turn_content="...", llm_client=_FakeLLM(payload))
    assert len(facts) == 1
    assert facts[0].object == "Rust"


async def test_extract_invalid_json_returns_empty() -> None:
    from fleetent.memory import facts_pipeline

    facts = await facts_pipeline.extract_facts(
        turn_content="...", llm_client=_FakeLLM("not json at all")
    )
    assert facts == []


async def test_extract_injects_known_relations_into_prompt() -> None:
    from fleetent.memory import facts_pipeline

    llm = _FakeLLM("[]")
    await facts_pipeline.extract_facts(
        turn_content="I have 8 years of experience",
        llm_client=llm,
        known_relations=["years_of_experience", "is_role", "located_in"],
    )
    system_msg = next(m["content"] for m in llm.last_messages if m["role"] == "system")
    # The known relation wordlist must be surfaced so the LLM reuses it.
    assert "years_of_experience" in system_msg
    assert "located_in" in system_msg


async def test_reuse_instruction_prefers_fidelity_over_reuse() -> None:
    from fleetent.memory import facts_pipeline

    # Reuse must be conditioned on SAME MEANING; the prompt must forbid bending
    # meaning to reuse (the "ate pancakes" → likes failure mode).
    prompt = facts_pipeline._extract_system_prompt(["likes", "ate"])
    assert "same meaning" in prompt.lower()
    # The relation must agree with the statement (no ate→likes drift).
    assert "likes" in prompt and "ate" in prompt


async def test_extract_system_prompt_guides_name_relation() -> None:
    from fleetent.memory import facts_pipeline

    # The base system prompt must steer name/alias facts to the canonical `name`
    # relation instead of letting the model coin `knows_as`, `called`, etc.
    prompt = facts_pipeline._extract_system_prompt(None)
    assert "name" in prompt.lower()


async def test_extract_prompt_excludes_tasks_and_hallucination() -> None:
    from fleetent.memory import facts_pipeline

    # Task/command intents ("提醒我做X") are to-dos, not facts; and the model must
    # not invent facts not stated (the "提醒我测试" → is_role=designer hallucination).
    prompt = facts_pipeline._extract_system_prompt(None)
    low = prompt.lower()
    assert "remind me to" in low or "提醒我做x" in prompt
    assert "do not invent" in low or "do not infer" in low
    assert "designer" in low  # the explicit anti-hallucination example


async def test_extract_system_prompt_guides_subject() -> None:
    from fleetent.memory import facts_pipeline

    # The prompt must teach the model to set subject by who the fact is about:
    # the user, the assistant/agent, or a named third party — not always "user".
    prompt = facts_pipeline._extract_system_prompt(None).lower()
    assert "agent" in prompt  # facts about the assistant get subject="agent"
    assert "subject" in prompt


async def test_extract_normalizes_user_aliases_to_canonical_subject() -> None:
    from fleetent.memory import facts_pipeline

    # The LLM sometimes emits 用户 / 我 / me for the user and 助手 / 你 for the agent.
    # These must be normalized to the canonical 'user' / 'agent' tokens so the same
    # subject is never split into duplicates (the user vs 用户 duplication bug).
    payload = json.dumps(
        [
            {"subject": "用户", "relation": "name", "object": "Xin", "temporal": "none"},
            {"subject": "助手", "relation": "name", "object": "小派", "temporal": "none"},
            {"subject": "张三", "relation": "works_at", "object": "Acme", "temporal": "none"},
        ]
    )
    facts = await facts_pipeline.extract_facts("...", llm_client=_FakeLLM(payload))
    by_obj = {f.object: f.subject for f in facts}
    assert by_obj["Xin"] == "user"  # 用户 → user
    assert by_obj["小派"] == "agent"  # 助手 → agent
    assert by_obj["Acme"] == "张三"  # named third party kept as-is


async def test_extract_normalizes_user_own_name_to_user_subject() -> None:
    from fleetent.memory import facts_pipeline

    # The user's own name (known from a prior name fact) used as a subject must be
    # folded back to 'user', or the same person splits into user vs Xin duplicates.
    payload = json.dumps(
        [
            {"subject": "Xin", "relation": "works_at", "object": "Acme", "temporal": "none"},
            {"subject": "张三", "relation": "works_at", "object": "Beta", "temporal": "none"},
        ]
    )
    facts = await facts_pipeline.extract_facts(
        "...", llm_client=_FakeLLM(payload), user_aliases={"xin"}
    )
    by_obj = {f.object: f.subject for f in facts}
    assert by_obj["Acme"] == "user"  # own name Xin → user
    assert by_obj["Beta"] == "张三"  # third party unaffected


async def test_extract_agent_subject_fact() -> None:
    from fleetent.memory import facts_pipeline

    payload = json.dumps(
        [{"subject": "agent", "relation": "name", "object": "小派", "valid_until": None}]
    )
    facts = await facts_pipeline.extract_facts(
        turn_content="记住你叫小派", llm_client=_FakeLLM(payload)
    )
    assert len(facts) == 1
    assert facts[0].subject == "agent"
    assert facts[0].relation == "name"
    assert facts[0].object == "小派"


async def test_extract_parses_statement() -> None:
    from fleetent.memory import facts_pipeline

    payload = json.dumps(
        [
            {
                "subject": "user",
                "relation": "name",
                "object": "Xin",
                "valid_until": None,
                "statement": "用户的名字是 Xin",
            }
        ]
    )
    facts = await facts_pipeline.extract_facts("我叫 Xin", llm_client=_FakeLLM(payload))
    assert facts[0].statement == "用户的名字是 Xin"


async def test_extract_missing_statement_is_none() -> None:
    from fleetent.memory import facts_pipeline

    # No statement key → RawFact.statement is None (injection falls back).
    payload = json.dumps(
        [{"subject": "user", "relation": "name", "object": "Xin", "valid_until": None}]
    )
    facts = await facts_pipeline.extract_facts("我叫 Xin", llm_client=_FakeLLM(payload))
    assert facts[0].statement is None


async def test_extract_system_prompt_mentions_statement() -> None:
    from fleetent.memory import facts_pipeline

    prompt = facts_pipeline._extract_system_prompt(None).lower()
    assert "statement" in prompt


async def test_extract_prompt_uses_temporal_enum_not_dates() -> None:
    from fleetent.memory import facts_pipeline

    # The model must emit a temporal LABEL (today/this_week/none), never a date —
    # the date is computed in code (facts_temporal). The prompt must list the
    # enum and explicitly forbid outputting a date.
    prompt = facts_pipeline._extract_system_prompt(None)
    low = prompt.lower()
    assert "temporal" in low
    for label in ("today", "this_week", "this_month", "none"):
        assert label in low
    assert "do not output any date" in low
    # One-off event vs ongoing state must still be distinguished by example.
    assert "薄饼" in prompt  # one-off event → 'today'
    assert "ongoing" in low  # durable state → 'none'


async def test_extract_without_known_relations_still_works() -> None:
    from fleetent.memory import facts_pipeline

    payload = json.dumps(
        [{"subject": "user", "relation": "is_role", "object": "dev", "valid_until": None}]
    )
    # Omitting known_relations keeps the old behavior (back-compat).
    facts = await facts_pipeline.extract_facts(turn_content="...", llm_client=_FakeLLM(payload))
    assert len(facts) == 1


async def test_prompt_guides_skill_naming_not_relation_folding() -> None:
    from fleetent.memory import facts_pipeline

    # Skills go to has_skill with a canonical object name, not knows_how_to_X /
    # object='true', so the same skill is not stored as near-duplicates.
    prompt = facts_pipeline._extract_system_prompt(None)
    low = prompt.lower()
    assert "has_skill" in low
    assert "knows_how_to_at_mention" in low  # the named anti-example
    assert "true" in low  # forbids object='true'


async def test_prompt_excludes_realtime_system_meta() -> None:
    from fleetent.memory import facts_pipeline

    # Tool count / live status / agent capability are not durable user facts.
    prompt = facts_pipeline._extract_system_prompt(None)
    assert "11" in prompt  # the tool-count anti-example
    low = prompt.lower()
    assert "real-time" in low or "system/meta" in low or "tool count" in low
