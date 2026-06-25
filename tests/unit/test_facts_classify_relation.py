"""Unit tests: classify_relation assigns a verdict to a resolved fact."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fleetent.memory.facts_models import Fact, ResolvedFact


def _existing_fact(obj: str) -> Fact:
    now = datetime.now(UTC)
    return Fact(
        fact_id="old",
        user_id="u1",
        subject="user",
        relation="is_role",
        object=obj,
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
    )


class _FakeLLM:
    def __init__(self, verdict: str) -> None:
        self._verdict = verdict
        self.chat = self  # allow llm.chat.completions.create
        self.completions = self

    async def create(self, **kwargs):
        class _Msg:
            def __init__(self, content: str) -> None:
                self.content = content

        class _Choice:
            def __init__(self, content: str) -> None:
                self.message = _Msg(content)

        class _Resp:
            def __init__(self, content: str) -> None:
                self.choices = [_Choice(content)]

        return _Resp(self._verdict)


async def test_classify_no_existing_returns_orthogonal() -> None:
    from fleetent.memory import facts_pipeline

    resolved = ResolvedFact(
        subject="user",
        relation="is_role",
        object="Go developer",
        temporal="none",
        cardinality="single",
    )
    classified = await facts_pipeline.classify_relation(
        resolved, existing_facts=[], llm_client=_FakeLLM("Contradict")
    )
    assert classified.verdict == "Orthogonal"


async def test_classify_returns_llm_verdict() -> None:
    from fleetent.memory import facts_pipeline

    resolved = ResolvedFact(
        subject="user",
        relation="is_role",
        object="Go developer",
        temporal="none",
        cardinality="single",
    )
    classified = await facts_pipeline.classify_relation(
        resolved,
        existing_facts=[_existing_fact("Java developer")],
        llm_client=_FakeLLM("Contradict"),
    )
    assert classified.verdict == "Contradict"


async def test_classify_unparseable_verdict_defaults_orthogonal() -> None:
    from fleetent.memory import facts_pipeline

    resolved = ResolvedFact(
        subject="user",
        relation="is_role",
        object="Go developer",
        temporal="none",
        cardinality="single",
    )
    classified = await facts_pipeline.classify_relation(
        resolved,
        existing_facts=[_existing_fact("Java developer")],
        llm_client=_FakeLLM("gibberish-not-a-verdict"),
    )
    assert classified.verdict == "Orthogonal"


async def test_classify_identical_object_is_equivalent_without_llm() -> None:
    from fleetent.memory import facts_pipeline

    # New object identical (case/space-insensitive) to an existing one must be
    # judged Equivalent deterministically, without consulting the LLM — so a
    # repeated "Fleetent" never gets stored twice.
    resolved = ResolvedFact(
        subject="agent",
        relation="name",
        object="  fleetent ",
        temporal="none",
        cardinality="single",
    )

    class _BoomLLM:
        chat = completions = None  # any access would blow up

        async def create(self, **kwargs):
            raise AssertionError("LLM must not be called for identical objects")

    classified = await facts_pipeline.classify_relation(
        resolved,
        existing_facts=[_existing_fact("Fleetent")],
        llm_client=_BoomLLM(),
    )
    assert classified.verdict == "Equivalent"
