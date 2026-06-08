from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock


from fleetent import observability
from fleetent.intelligence import reflection


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
        reflection.MemoryMaintenanceProposal(
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
    monkeypatch.setattr(reflection, "generate_memory_maintenance_proposals", lambda _user, _findings: memory_proposals)
    monkeypatch.setattr(reflection, "generate_skill_proposals", lambda *, findings=None, skill_signals=None: skill_proposals)
    persist_memory = []
    persist_skill = []
    monkeypatch.setattr(reflection, "_persist_memory_maintenance_proposal", lambda proposal: persist_memory.append(proposal))
    monkeypatch.setattr(reflection, "_persist_skill_proposal", lambda proposal: persist_skill.append(proposal))
    monkeypatch.setattr(reflection, "_save_report", lambda report: None)

    apply_memory = Mock()
    apply_skill = Mock()
    monkeypatch.setattr(reflection, "apply_memory_maintenance_proposal", apply_memory)
    monkeypatch.setattr(reflection, "apply_skill_proposal", apply_skill)
    monkeypatch.setattr(reflection, "_apply_maintenance_action", AsyncMock())

    result = await reflection.run_reflection("user-1")

    assert result is not None
    assert result.id
    assert len(persist_memory) == 1
    assert persist_memory[0] == memory_proposals[0]
    assert len(persist_skill) == 1
    assert persist_skill[0] == skill_proposals[0]
    apply_memory.assert_not_called()
    apply_skill.assert_not_called()


async def test_run_kb_reflection_report_is_read_only(monkeypatch) -> None:

    monkeypatch.setattr(observability, "query_trace_events", lambda query: [])
    monkeypatch.setattr(reflection, "_save_kb_reflection_report", lambda report: None)
    monkeypatch.setattr(reflection, "_connector_findings", Mock(return_value=[]))

    apply_memory = Mock()
    apply_skill = Mock()
    monkeypatch.setattr(reflection, "apply_memory_maintenance_proposal", apply_memory)
    monkeypatch.setattr(reflection, "apply_skill_proposal", apply_skill)

    result = await reflection.run_kb_reflection_report("tenant-a")

    assert result is not None
    apply_memory.assert_not_called()
    apply_skill.assert_not_called()
