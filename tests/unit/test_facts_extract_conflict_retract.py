"""Unit tests: extract_facts with active_facts snapshot triggers cross-relation conflict retract."""

from __future__ import annotations

import json
from datetime import UTC, datetime


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


def _make_fact(relation: str, obj: str) -> object:
    """Build a minimal Fact-like object for active_facts injection."""
    from fleetent.memory.facts_models import Fact

    now = datetime.now(UTC).replace(microsecond=0)
    return Fact(
        fact_id="test-id",
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
    )


async def test_extract_with_conflict_returns_forget_directive() -> None:
    """LLM sees existing prefers_language=Rust, user says dislike → forget emitted."""
    from fleetent.memory import facts_pipeline

    # LLM returns both the new dislikes fact AND a forget directive for the old one
    payload = json.dumps([
        {"subject": "user", "relation": "dislikes", "object": "Rust", "temporal": "none",
         "statement": "用户不喜欢 Rust"},
        {"subject": "user", "relation": "forget", "object": "Rust", "temporal": "none",
         "statement": "忘记 user 的 prefers_language=Rust"},
    ])
    active_facts = [_make_fact("prefers_language", "Rust")]

    facts = await facts_pipeline.extract_facts(
        turn_content="我不喜欢 Rust",
        llm_client=_FakeLLM(payload),
        active_facts=active_facts,
    )

    forget_facts = [f for f in facts if f.relation == "forget" and f.object == "Rust"]
    assert len(forget_facts) == 1, "应包含针对 Rust 的 forget 指令"


async def test_extract_no_conflict_no_forget_directive() -> None:
    """User says like Go, existing prefers_language=Rust → no forget for Rust."""
    from fleetent.memory import facts_pipeline

    payload = json.dumps([
        {"subject": "user", "relation": "prefers_language", "object": "Go", "temporal": "none",
         "statement": "用户也喜欢 Go"},
    ])
    active_facts = [_make_fact("prefers_language", "Rust")]

    facts = await facts_pipeline.extract_facts(
        turn_content="我也喜欢 Go",
        llm_client=_FakeLLM(payload),
        active_facts=active_facts,
    )

    forget_facts = [f for f in facts if f.relation == "forget" and f.object == "Rust"]
    assert len(forget_facts) == 0, "非矛盾场景不应生成针对 Rust 的 forget 指令"


async def test_extract_empty_active_facts_no_error() -> None:
    """active_facts=[] should not raise and return extracted facts normally."""
    from fleetent.memory import facts_pipeline

    payload = json.dumps([
        {"subject": "user", "relation": "is_role", "object": "dev", "temporal": "none"},
    ])

    facts = await facts_pipeline.extract_facts(
        turn_content="I am a developer",
        llm_client=_FakeLLM(payload),
        active_facts=[],
    )

    assert len(facts) == 1
    assert facts[0].relation == "is_role"


async def test_active_facts_injected_into_user_message() -> None:
    """When active_facts non-empty, user message must contain the snapshot section."""
    from fleetent.memory import facts_pipeline

    llm = _FakeLLM("[]")
    active_facts = [
        _make_fact("prefers_language", "Rust"),
        _make_fact("likes", "Python"),
    ]

    await facts_pipeline.extract_facts(
        turn_content="test content",
        llm_client=llm,
        active_facts=active_facts,
    )

    user_msg = next(m["content"] for m in llm.last_messages if m["role"] == "user")
    assert "已有记忆" in user_msg or "[existing memories]" in user_msg.lower()
    assert "prefers_language" in user_msg
    assert "Rust" in user_msg
    assert "likes" in user_msg
    assert "Python" in user_msg


async def test_active_facts_none_behaves_same_as_before() -> None:
    """Omitting active_facts (None) keeps backward-compatible behavior."""
    from fleetent.memory import facts_pipeline

    payload = json.dumps([
        {"subject": "user", "relation": "is_role", "object": "dev", "temporal": "none"},
    ])

    facts = await facts_pipeline.extract_facts(
        turn_content="I am a developer",
        llm_client=_FakeLLM(payload),
    )

    assert len(facts) == 1
    assert facts[0].relation == "is_role"
