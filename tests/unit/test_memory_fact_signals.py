"""Unit tests: facts_pipeline emits memory_fact_observed trace signals."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from fleetent.memory.facts_models import Fact
from fleetent.memory.facts_pipeline import _emit_memory_fact_signals, run_pipeline


def _fact(fid: str, statement: str = "", relation: str = "works_at", obj: str = "ACME") -> Fact:
    now = datetime.now(UTC).replace(microsecond=0)
    return Fact(
        fact_id=fid,
        user_id="u1",
        subject="user",
        relation=relation,
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
        statement=statement or None,
        scope="situational",
    )


# ── _emit_memory_fact_signals ──────────────────────────────────────────────────


def test_emit_uses_statement_when_present() -> None:
    fact = _fact("f1", statement="用户在 ACME 公司工作")
    with patch("fleetent.memory.facts_pipeline.record_trace_event") as mock_record:
        # need to import inside patch scope
        import fleetent.memory.facts_pipeline as fp
        from fleetent.observability.traces import record_trace_event  # noqa: F401

        fp._emit_memory_fact_signals(
            [fact], user_id="u1", run_id="run-1", agent_name="bot"
        )
    mock_record.assert_called_once()
    event = mock_record.call_args[0][0]
    assert event.payload["memory_fact"] == "用户在 ACME 公司工作"
    assert event.event_type == "memory_fact_observed"
    assert event.user_id == "u1"
    assert event.agent_name == "bot"
    assert event.run_id == "run-1"


def test_emit_falls_back_to_triple_when_no_statement() -> None:
    fact = _fact("f2", statement="")
    with patch("fleetent.memory.facts_pipeline.record_trace_event") as mock_record:
        import fleetent.memory.facts_pipeline as fp

        fp._emit_memory_fact_signals(
            [fact], user_id="u1", run_id="run-1", agent_name=None
        )
    mock_record.assert_called_once()
    payload = mock_record.call_args[0][0].payload["memory_fact"]
    assert "works_at" in payload
    assert "ACME" in payload


def test_emit_skips_when_run_id_none() -> None:
    fact = _fact("f3", statement="some fact")
    with patch("fleetent.memory.facts_pipeline.record_trace_event") as mock_record:
        import fleetent.memory.facts_pipeline as fp

        fp._emit_memory_fact_signals(
            [fact], user_id="u1", run_id=None, agent_name="bot"
        )
    mock_record.assert_not_called()


def test_emit_skips_empty_list() -> None:
    with patch("fleetent.memory.facts_pipeline.record_trace_event") as mock_record:
        import fleetent.memory.facts_pipeline as fp

        fp._emit_memory_fact_signals([], user_id="u1", run_id="run-1", agent_name=None)
    mock_record.assert_not_called()


def test_emit_emits_one_event_per_fact() -> None:
    facts = [_fact(f"f{i}", statement=f"fact {i}") for i in range(3)]
    with patch("fleetent.memory.facts_pipeline.record_trace_event") as mock_record:
        import fleetent.memory.facts_pipeline as fp

        fp._emit_memory_fact_signals(facts, user_id="u1", run_id="run-1", agent_name=None)
    assert mock_record.call_count == 3


def test_emit_does_not_raise_on_trace_error() -> None:
    fact = _fact("f4", statement="should not raise")
    with patch(
        "fleetent.memory.facts_pipeline.record_trace_event",
        side_effect=RuntimeError("db not wired"),
    ):
        import fleetent.memory.facts_pipeline as fp

        # must not raise
        fp._emit_memory_fact_signals(
            [fact], user_id="u1", run_id="run-1", agent_name=None
        )


# ── _confirmed_facts_for_signals ──────────────────────────────────────────────


def test_confirmed_facts_for_signals_returns_equivalent(monkeypatch) -> None:
    import fleetent.memory.facts_pipeline as fp
    from fleetent.memory.facts_models import ClassifiedFact

    existing = _fact("ex1", statement="用户在 NSD 工作")
    cf = ClassifiedFact(
        subject="user", relation="works_at", object="NSD",
        cardinality="single", verdict="Equivalent", scope="situational",
    )

    import fleetent.memory.facts_store as store
    monkeypatch.setattr(store, "active_facts_for_relation", lambda uid, subj, rel: [existing])

    result = fp._confirmed_facts_for_signals("u1", [cf])
    assert result == [existing]


def test_confirmed_facts_skips_non_recurrence_verdicts(monkeypatch) -> None:
    import fleetent.memory.facts_pipeline as fp
    from fleetent.memory.facts_models import ClassifiedFact

    called = []
    import fleetent.memory.facts_store as store
    monkeypatch.setattr(
        store, "active_facts_for_relation",
        lambda uid, subj, rel: called.append(rel) or [],
    )

    for verdict in ("Orthogonal", "Contradict", "Subsumes"):
        cf = ClassifiedFact(
            subject="user", relation="works_at", object="X",
            cardinality="single", verdict=verdict, scope="situational",
        )
        fp._confirmed_facts_for_signals("u1", [cf])

    assert called == []  # none of these verdicts should trigger a lookup


# ── run_pipeline passes run_id / agent_name through ───────────────────────────


async def test_run_pipeline_passes_run_id_to_emit(monkeypatch) -> None:
    """run_pipeline calls _emit_memory_fact_signals with the supplied run_id."""
    import fleetent.memory.facts_pipeline as fp
    from fleetent.memory.facts_models import ClassifiedFact, RawFact, ResolvedFact

    now = datetime.now(UTC).replace(microsecond=0)
    raw = RawFact(subject="user", relation="works_at", object="ACME", scope="situational")
    resolved = ResolvedFact(subject="user", relation="works_at", object="ACME",
                            cardinality="single", scope="situational")
    classified = ClassifiedFact(subject="user", relation="works_at", object="ACME",
                                cardinality="single", verdict="New", scope="situational")
    committed_facts = [_fact("f5", statement="工作地点在北京")]

    monkeypatch.setattr(fp, "extract_facts", AsyncMock(return_value=[raw]))
    monkeypatch.setattr(fp, "resolve_relation", AsyncMock(return_value=resolved))
    monkeypatch.setattr(fp, "classify_relation", AsyncMock(return_value=classified))
    monkeypatch.setattr(fp, "_commit_facts", lambda *a, **kw: committed_facts)
    monkeypatch.setattr(fp, "_sync_vectors", AsyncMock())
    monkeypatch.setattr(fp, "_relation_store", lambda: MagicMock(list_relation_clusters=lambda: []))
    monkeypatch.setattr(fp, "_known_user_aliases", lambda uid: [])
    monkeypatch.setattr(fp, "_all_active_facts_for_user", lambda uid: [])
    monkeypatch.setattr(fp, "_active_facts_for_relation", lambda *a: [])

    emitted: list = []
    monkeypatch.setattr(fp, "_emit_memory_fact_signals", lambda facts, **kw: emitted.append(kw))

    await fp.run_pipeline(
        user_id="u1",
        turn_content="我在北京工作",
        db=MagicMock(),
        vector_backend=MagicMock(),
        llm_client=MagicMock(),
        source_turn="sess-1",
        run_id="run-abc",
        agent_name="my-bot",
    )

    assert len(emitted) == 1
    assert emitted[0]["run_id"] == "run-abc"
    assert emitted[0]["agent_name"] == "my-bot"
    assert emitted[0]["user_id"] == "u1"
