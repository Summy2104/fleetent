from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from fleetent import observability, reflection
from fleetent.reflection import reflection as reflection_impl


async def test_run_reflection_generates_pending_proposals_without_auto_apply(
    monkeypatch,
) -> None:
    fake_events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers Python for backend work"},
            user_id="user-1",
        ),
        observability.TraceEvent(
            id="trace-2",
            run_id="run-2",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers Python for backend work"},
            user_id="user-1",
        ),
    ]

    memory_proposals = [
        reflection.MemoryProposal(
            id="memory-proposal-1",
            user_id="user-1",
            action="rewrite",
            target_memory_ids=[],
            proposed_content="User prefers Python for backend work",
            metadata_patch={"confirmation": "inline", "source_finding": "memory_candidate"},
            risk="medium",
            reason="Repeated user fact may belong in memory",
            evidence_ids=["trace-1", "trace-2"],
            status="pending",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            expires_at=None,
        )
    ]
    skill_proposals = [
        reflection.SkillProposal(
            id="skill-proposal-1",
            type="create_skill",
            target_skill="status_report",
            reason="Repeated task pattern may become skill",
            evidence_refs=["trace-3", "trace-4"],
            risk_level="low",
            suggested_draft="Draft skill status_report",
            suggested_diff=None,
            status="pending",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]

    monkeypatch.setattr(observability, "query_trace_events", lambda query: fake_events)
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        reflection_impl,
        "generate_memory_maintenance_proposals",
        lambda _user, _findings, report_id=None: memory_proposals,
    )
    monkeypatch.setattr(
        reflection_impl,
        "generate_skill_proposals",
        lambda *, findings=None, skill_signals=None, report_id=None: skill_proposals,
    )
    persist_memory = []
    persist_skill = []
    monkeypatch.setattr(
        reflection_impl,
        "_persist_memory_maintenance_proposal",
        lambda proposal: persist_memory.append(proposal),
    )
    monkeypatch.setattr(
        reflection_impl, "_persist_skill_proposal", lambda proposal: persist_skill.append(proposal)
    )
    monkeypatch.setattr(reflection_impl, "_save_report", lambda report: None)

    apply_memory = Mock()
    apply_skill = Mock()
    monkeypatch.setattr(reflection, "apply_memory_maintenance_proposal", apply_memory)
    monkeypatch.setattr(reflection, "apply_skill_proposal", apply_skill)
    monkeypatch.setattr(reflection_impl, "_apply_maintenance_action", AsyncMock())

    result = await reflection.run_reflection("user-1")

    assert result is not None
    assert result.id
    assert len(persist_memory) == 1
    assert persist_memory[0] == memory_proposals[0]
    assert len(persist_skill) == 1
    assert persist_skill[0] == skill_proposals[0]
    apply_memory.assert_not_called()
    apply_skill.assert_not_called()


async def test_run_reflection_auto_apply_attempts_each_memory_proposal_only_when_enabled(
    monkeypatch,
) -> None:
    fake_events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers Python for backend work"},
            user_id="user-1",
        )
    ]
    mark_stale = reflection.MemoryProposal(
        id="memory-proposal-1",
        user_id="user-1",
        action="mark_stale",
        target_memory_ids=["memory-1"],
        proposed_content=None,
        metadata_patch={},
        risk="low",
        reason="Mark stale",
        evidence_ids=["trace-1"],
        status="pending",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=None,
    )
    shared_suggestion = reflection.MemoryProposal(
        id="memory-proposal-2",
        user_id="user-1",
        action="suggest_agent_memory_or_kb",
        target_memory_ids=[],
        proposed_content="Team preference",
        metadata_patch={"target": "agent_memory"},
        risk="low",
        reason="Promote shared knowledge",
        evidence_ids=["trace-1"],
        status="pending",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=None,
    )

    monkeypatch.setattr(observability, "query_trace_events", lambda query: fake_events)
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        reflection_impl,
        "generate_memory_maintenance_proposals",
        lambda _user, _findings, report_id=None: [mark_stale, shared_suggestion],
    )
    monkeypatch.setattr(
        reflection_impl,
        "generate_skill_proposals",
        lambda *, findings=None, skill_signals=None, report_id=None: [],
    )
    monkeypatch.setattr(reflection_impl, "_save_report", lambda report: None)
    monkeypatch.setattr(reflection_impl, "_persist_skill_proposal", lambda proposal: None)

    persisted: list[str] = []
    applied: list[str] = []
    def persist(proposal: reflection.MemoryProposal) -> None:
        persisted.append(proposal.id)

    async def apply(proposal_id: str, *, actor_user_id=None, auto_policy=None) -> None:
        assert actor_user_id is None
        assert auto_policy is not None
        applied.append(proposal_id)
        if proposal_id == shared_suggestion.id:
            raise PermissionError("owner approval is required")

    monkeypatch.setattr(reflection_impl, "_persist_memory_maintenance_proposal", persist)
    monkeypatch.setattr(reflection, "apply_memory_maintenance_proposal", apply)

    await reflection.run_reflection(
        "user-1",
        auto_policy=reflection.AutoMaintenancePolicy(allow_low_risk=True),
    )
    assert persisted == [mark_stale.id, shared_suggestion.id]
    assert applied == [mark_stale.id, shared_suggestion.id]

    persisted.clear()
    applied.clear()
    await reflection.run_reflection("user-1")
    assert persisted == [mark_stale.id, shared_suggestion.id]
    assert applied == []


async def test_run_reflection_auto_apply_failures_are_bulkeaded(
    monkeypatch,
) -> None:
    fake_events = [
        observability.TraceEvent(
            id="trace-1",
            run_id="run-1",
            event_type="agent_run_completed",
            payload={"memory_fact": "User prefers Python for backend work"},
            user_id="user-1",
        )
    ]
    first = reflection.MemoryProposal(
        id="memory-proposal-1",
        user_id="user-1",
        action="mark_stale",
        target_memory_ids=["memory-1"],
        proposed_content=None,
        metadata_patch={},
        risk="low",
        reason="Mark stale",
        evidence_ids=["trace-1"],
        status="pending",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=None,
    )
    second = reflection.MemoryProposal(
        id="memory-proposal-2",
        user_id="user-1",
        action="mark_stale",
        target_memory_ids=["memory-2"],
        proposed_content=None,
        metadata_patch={},
        risk="low",
        reason="Mark stale",
        evidence_ids=["trace-1"],
        status="pending",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        expires_at=None,
    )

    monkeypatch.setattr(observability, "query_trace_events", lambda query: fake_events)
    monkeypatch.setattr(reflection.memory, "search", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        reflection_impl,
        "generate_memory_maintenance_proposals",
        lambda _user, _findings, report_id=None: [first, second],
    )
    monkeypatch.setattr(
        reflection_impl,
        "generate_skill_proposals",
        lambda *, findings=None, skill_signals=None, report_id=None: [],
    )
    monkeypatch.setattr(reflection_impl, "_save_report", lambda report: None)
    monkeypatch.setattr(reflection_impl, "_persist_skill_proposal", lambda proposal: None)

    persisted: list[str] = []
    applied: list[str] = []

    monkeypatch.setattr(
        reflection_impl,
        "_persist_memory_maintenance_proposal",
        lambda proposal: persisted.append(proposal.id),
    )

    async def apply(proposal_id: str, *, actor_user_id=None, auto_policy=None) -> None:
        if proposal_id == first.id:
            raise RuntimeError("boom")
        applied.append(proposal_id)

    mock_logger = Mock()
    monkeypatch.setattr(reflection, "apply_memory_maintenance_proposal", apply)
    monkeypatch.setattr(reflection_impl, "_logger", mock_logger, raising=False)

    result = await reflection.run_reflection(
        "user-1",
        auto_policy=reflection.AutoMaintenancePolicy(allow_low_risk=True),
    )

    assert result is not None
    assert persisted == [first.id, second.id]
    assert applied == [second.id]
    assert mock_logger.warn.called


async def test_run_kb_reflection_report_is_read_only(monkeypatch) -> None:

    monkeypatch.setattr(observability, "query_trace_events", lambda query: [])
    monkeypatch.setattr(reflection_impl, "_save_kb_reflection_report", lambda report: None)
    monkeypatch.setattr(reflection_impl, "_connector_findings", Mock(return_value=[]))

    apply_memory = Mock()
    apply_skill = Mock()
    monkeypatch.setattr(reflection, "apply_memory_maintenance_proposal", apply_memory)
    monkeypatch.setattr(reflection, "apply_skill_proposal", apply_skill)

    result = await reflection.run_kb_reflection_report("tenant-a")

    assert result is not None
    apply_memory.assert_not_called()
    apply_skill.assert_not_called()
