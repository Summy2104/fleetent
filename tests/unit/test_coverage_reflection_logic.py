from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from fleetent import observability, reflection
from fleetent.memory.models import MemoryItem


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None, row: dict[str, Any] | None = None):
        self._rows = rows or []
        self._row = row

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _ReflectionDb:
    def __init__(self) -> None:
        self.path = SimpleNamespace(exists=lambda: True)
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.tables = {
            "reflection_reports",
            "reflection_proposals",
        }
        self.rows_by_table: dict[str, list[dict[str, Any]]] = {}
        self.row_by_id: dict[str, dict[str, Any]] = {}

    def execute(self, sql: str, params: dict[str, object] | None = None) -> _Cursor:
        params = params or {}
        self.executed.append((sql, params))
        if "sqlite_master" in sql:
            name = str(params["name"])
            return _Cursor(row={"name": name} if name in self.tables else None)
        if "FROM reflection_reports" in sql:
            rows = self.rows_by_table.get("reflection_reports", [])
            domain = params.get("domain")
            domain_keys = sorted(key for key in params if key.startswith("domain_"))
            if domain_keys:
                allowed = {str(params[key]) for key in domain_keys}
                rows = [row for row in rows if row.get("domain") in allowed]
            elif domain is not None:
                rows = [row for row in rows if row.get("domain") == domain]
            return _Cursor(rows)
        if "FROM reflection_proposals" in sql and "WHERE id = :id" in sql:
            return _Cursor(row=self.row_by_id.get(str(params["id"])))
        if "FROM reflection_proposals" in sql:
            rows = self.rows_by_table.get("reflection_proposals", [])
            domain = params.get("domain")
            if domain is not None:
                rows = [row for row in rows if row.get("domain") == domain]
            elif "domain = 'memory'" in sql:
                rows = [row for row in rows if row.get("domain") == "memory"]
            elif "domain = 'skill'" in sql:
                rows = [row for row in rows if row.get("domain") == "skill"]
            return _Cursor(rows)
        return _Cursor()


def _event(
    run_id: str,
    payload: dict[str, Any],
    *,
    id: str | None = None,
    tenant_id: str = "tenant",
) -> observability.TraceEvent:
    return observability.TraceEvent(
        run_id=run_id,
        event_type="test",
        payload=payload,
        id=id,
        tenant_id=tenant_id,
    )


def _memory(id: str, content: str) -> MemoryItem:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return MemoryItem(
        id=id,
        user_id="u1",
        type="identity",
        content=content,
        created_at=now,
        updated_at=now,
        expires_at=None,
    )


def _maintenance_proposal(
    *,
    id: str = "mp1",
    user_id: str = "u1",
    action: str = "mark_stale",
    status: str = "pending",
    risk: str = "low",
    target_memory_ids: list[str] | None = None,
    proposed_content: str | None = "New content",
    metadata_patch: dict[str, str] | None = None,
    expires_at: datetime | None = None,
) -> reflection.MemoryProposal:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return reflection.MemoryProposal(
        id=id,
        user_id=user_id,
        action=action,  # type: ignore[arg-type]
        target_memory_ids=target_memory_ids if target_memory_ids is not None else ["m1"],
        proposed_content=proposed_content,
        metadata_patch=metadata_patch or {},
        risk=risk,  # type: ignore[arg-type]
        reason="because",
        evidence_ids=["e1"],
        status=status,  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
    )


def _skill_proposal(
    *,
    id: str = "sp1",
    status: str = "pending",
    type: str = "create_skill",
) -> reflection.SkillProposal:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return reflection.SkillProposal(
        id=id,
        type=type,  # type: ignore[arg-type]
        target_skill="triage-alerts",
        reason="Repeated work",
        evidence_refs=["e1", "e2"],
        risk_level="medium",
        suggested_draft="---\nname: triage-alerts\ndescription: triage alerts\n---\nbody",
        suggested_diff=None,
        status=status,  # type: ignore[arg-type]
        created_at=now,
        updated_at=now,
    )


def test_reflection_finding_generation_and_text_extraction():
    events = [
        _event("r1", {"memory_fact": "User likes tea", "task_pattern": "triage alerts"}),
        _event("r2", {"memory_fact": "User likes tea", "task_pattern": "triage alerts"}),
        _event("r3", {"nested": {"text": ["alpha", {"more": "beta"}]}}),
    ]
    memories = [
        _memory("m1", "User role is engineer"),
        _memory("m2", "User role is manager"),
        _memory("m3", "not parseable"),
    ]

    findings = reflection._generate_findings(events, memories)  # noqa: SLF001

    assert {finding.type for finding in findings} == {
        "memory_candidate",
        "memory_conflict",
        "skill_opportunity",
    }
    assert reflection._events_to_text(events) == (  # noqa: SLF001
        "User likes tea\ntriage alerts\nUser likes tea\ntriage alerts\nalpha\nbeta"
    )
    assert reflection._parse_memory_field_value("User role is engineer") == (  # noqa: SLF001
        "role",
        "engineer",
    )
    assert reflection._parse_memory_field_value("No marker") is None  # noqa: SLF001
    assert reflection._event_evidence_id(_event("run", {}, id="event-id")) == "event-id"  # noqa: SLF001


def test_reflection_generates_memory_and_skill_proposals(monkeypatch):
    memory_proposals: list[reflection.MemoryProposal] = []
    skill_proposals: list[reflection.SkillProposal] = []
    # Neutralize persistence so this unit test exercises only generation logic; the
    # _persist_* wrappers are the ones that reach _database() (no _state_db injected here).
    monkeypatch.setattr(reflection, "_persist_memory_maintenance_proposal", lambda proposal: None)
    monkeypatch.setattr(reflection, "_persist_skill_proposal", lambda proposal: None)

    findings = [
        reflection.ReflectionFinding(
            type="memory_candidate",
            summary="Remember team process",
            evidence_ids=["e1", "e2"],
            metadata={"fact": "team deploys on Friday"},
        ),
        reflection.ReflectionFinding(
            type="memory_candidate",
            summary="Remember personal preference",
            evidence_ids=["e3", "e4"],
            metadata={"fact": "User prefers terse updates"},
        ),
        reflection.ReflectionFinding(
            type="memory_candidate",
            summary="Empty",
            evidence_ids=["e5"],
            metadata={"fact": " "},
        ),
        reflection.ReflectionFinding(
            type="memory_conflict",
            summary="Conflict",
            evidence_ids=["m1", "m2"],
            metadata={},
        ),
    ]

    memory_proposals.extend(reflection.generate_memory_maintenance_proposals("u1", findings))
    assert [proposal.action for proposal in memory_proposals] == [
        "suggest_agent_memory_or_kb",
        "rewrite",
        "merge",
    ]
    assert memory_proposals[0].metadata_patch["boundary"] == (
        "not_user_memory:suggest_agent_memory_or_kb"
    )

    skill_proposals.extend(
        reflection.generate_skill_proposals(
            findings=[
                reflection.ReflectionFinding(
                    type="skill_opportunity",
                    summary="Repeated task pattern may become a skill: triage alerts quickly",
                    evidence_ids=["e1", "e2"],
                    metadata={},
                ),
                reflection.ReflectionFinding(
                    type="skill_opportunity",
                    summary="ignored",
                    evidence_ids=["only-one"],
                    metadata={"pattern": "ignored"},
                ),
            ],
            skill_signals=[
                {
                    "skill_name": "broken-skill",
                    "trigger_count": 9,
                    "failure_count": 3,
                    "reason": "frequent failures",
                },
                {
                    "skill_name": "unused-skill",
                    "trigger_count": 0,
                    "days_unused": 120.0,
                    "reason": "unused",
                },
                {"skill_name": " ", "trigger_count": 10},
            ],
        )
    )
    assert [proposal.type for proposal in skill_proposals] == [
        "create_skill",
        "update_skill",
        "deprecate_skill",
    ]
    assert skill_proposals[0].target_skill == "triage-alerts-quickly"
    assert "frequent failures" in skill_proposals[1].suggested_diff
    assert "120 unused days" in skill_proposals[2].suggested_diff


def test_reflection_kb_findings_cover_quality_graph_and_connector_paths(monkeypatch):
    events = [
        _event("zero", {"query": "missing answer", "result_count": 0}, id="e0"),
        _event(
            "stale",
            {
                "question": "service dependency relationship",
                "result_count": 2,
                "stale_document_id": "doc1",
                "top_score": 0.2,
                "source_attribution_count": 0,
                "graph_result_count": 0,
                "graph_evidence_count": 0,
            },
            id="e1",
        ),
        _event("corrected", {"query": "corrected", "result_count": 1, "user_correction": True}),
    ]

    findings = reflection._generate_kb_findings(events)  # noqa: SLF001
    assert [finding.type for finding in findings] == [
        "missing_knowledge",
        "stale_document",
        "low_retrieval_quality",
        "entity_graph_gap",
        "low_retrieval_quality",
    ]
    assert reflection._int_payload({"count": 3.8}, "count") == 3  # noqa: SLF001
    assert reflection._int_payload({"count": "3"}, "count") is None  # noqa: SLF001

    monkeypatch.setattr(
        reflection.knowledge_base,
        "list_configured_connectors",
        lambda: [SimpleNamespace(connector_id="c1"), SimpleNamespace(connector_id="c2")],
    )
    monkeypatch.setattr(
        reflection.knowledge_base,
        "get_connector_status",
        lambda connector_id: (
            SimpleNamespace(status="failed", error_summary="bad credentials")
            if connector_id == "c1"
            else SimpleNamespace(status="ok", error_summary="")
        ),
    )
    connector_findings = reflection._connector_findings()  # noqa: SLF001
    assert [(finding.type, finding.severity) for finding in connector_findings] == [
        ("connector_sync_issue", "high")
    ]

    monkeypatch.setattr(
        reflection.knowledge_base,
        "list_configured_connectors",
        lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    assert reflection._connector_findings()[0].metadata == {  # noqa: SLF001
        "reason": "knowledge_base_unavailable"
    }


def test_reflection_trend_summary_aggregates_fake_database(monkeypatch):
    db = _ReflectionDb()
    db.rows_by_table["reflection_reports"] = [
        {
            "domain": "memory",
            "findings_json": json.dumps(
                [{"type": "memory_candidate"}, {"type": "skill_opportunity"}, "ignored"]
            ),
            "created_at": "2026-01-01T02:00:00+00:00",
        },
        {
            "domain": "knowledge_base",
            "findings_json": json.dumps([{"type": "missing_knowledge"}]),
            "created_at": "2026-01-02T02:00:00+00:00",
        },
    ]
    db.rows_by_table["reflection_proposals"] = [
        {
            "domain": "memory",
            "kind": "delete",
            "risk": "high",
            "status": "applied",
            "created_at": "2026-01-01T03:00:00+00:00",
        },
        {
            "domain": "memory",
            "kind": "merge",
            "risk": "medium",
            "status": "rejected",
            "created_at": "2026-01-02T03:00:00+00:00",
        },
        {
            "domain": "skill",
            "kind": "create_skill",
            "risk": "medium",
            "status": "applied",
            "created_at": "2026-01-01T04:00:00+00:00",
        },
    ]
    monkeypatch.setattr(reflection, "_database", lambda: db)

    query = reflection.ReflectionTrendQuery(
        scope="global",
        start_ts=datetime(2026, 1, 1, tzinfo=UTC),
        end_ts=datetime(2026, 1, 3, tzinfo=UTC),
        bucket="day",
    )
    summary = reflection.get_reflection_trend_summary(query)

    assert summary.top_findings == [
        "memory_candidate",
        "missing_knowledge",
        "skill_opportunity",
    ]
    assert summary.buckets[0].finding_counts == {
        "memory_candidate": 1,
        "skill_opportunity": 1,
    }
    assert summary.buckets[0].proposal_status_counts == {"applied": 2}
    assert summary.buckets[0].proposal_risk_counts == {"high": 1, "medium": 1}
    assert summary.buckets[0].proposal_action_counts == {"delete": 1}
    assert summary.buckets[0].proposal_type_counts == {"create_skill": 1}
    assert summary.buckets[0].applied_ratio == 1.0
    assert summary.buckets[1].finding_counts == {"missing_knowledge": 1}
    assert summary.buckets[1].rejected_ratio == 1.0

    with pytest.raises(ValueError, match="end_ts"):
        reflection._trend_bucket_ranges(  # noqa: SLF001
            reflection.ReflectionTrendQuery("u1", query.start_ts, query.start_ts, "day")
        )
    with pytest.raises(ValueError, match="unsupported"):
        reflection._trend_bucket_ranges(  # noqa: SLF001
            reflection.ReflectionTrendQuery("u1", query.start_ts, query.end_ts, "month")  # type: ignore[arg-type]
        )
    assert reflection._trend_findings_from_json("{}") == []  # noqa: SLF001
    assert reflection._trend_bucket_index(query.end_ts, [(query.start_ts, query.end_ts)]) is None  # noqa: SLF001


def test_reflection_save_and_row_mapping_helpers(monkeypatch):
    db = _ReflectionDb()
    monkeypatch.setattr(reflection, "_database", lambda: db)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    finding = reflection.ReflectionFinding(
        type="memory_candidate",
        summary="summary",
        evidence_ids=["e1"],
        metadata={"fact": "fact"},
    )
    kb_finding = reflection.KnowledgeBaseReflectionFinding(
        type="missing_knowledge",
        severity="high",
        affected_resource="query:q",
        evidence_refs=["e1"],
        recommendation="Add docs",
        metadata={"query": "q"},
    )

    reflection._save_report(  # noqa: SLF001
        reflection.ReflectionReport("r", "u1", (now, now + timedelta(days=1)), [finding], now)
    )
    reflection._save_kb_reflection_report(  # noqa: SLF001
        reflection.KnowledgeBaseReflectionReport(
            "kb",
            "tenant",
            (now, now + timedelta(days=1)),
            [kb_finding],
            now,
            {"trace_count": 1},
        )
    )
    assert any("INSERT INTO reflection_reports" in sql for sql, _params in db.executed)
    assert sum("INSERT INTO reflection_reports" in sql for sql, _params in db.executed) == 2
    assert any(
        params.get("domain") == "knowledge_base"
        for sql, params in db.executed
        if "INSERT INTO reflection_reports" in sql
    )

    proposal = _maintenance_proposal(metadata_patch={"target": "shared_memory"})
    params = reflection._proposal_params(proposal)  # noqa: SLF001
    assert reflection._proposal_from_row(params).metadata_patch == {"target": "shared_memory"}  # noqa: SLF001
    assert reflection._format_datetime(None) is None  # noqa: SLF001
    assert reflection._parse_optional_datetime(None) is None  # noqa: SLF001
    with pytest.raises(TypeError, match="expected datetime"):
        reflection._parse_datetime(123)  # noqa: SLF001

    skill = _skill_proposal()
    skill_params = reflection._skill_proposal_params(skill)  # noqa: SLF001
    restored = reflection._skill_proposal_from_row(skill_params)  # noqa: SLF001
    assert restored.evidence_refs == ["e1", "e2"]
    assert reflection._replace_skill_proposal(restored, status="approved").status == "approved"  # noqa: SLF001
    with pytest.raises(ValueError, match="skill proposal must be approved"):
        reflection._require_skill_proposal_status(restored, {"approved"})  # noqa: SLF001


def test_reflection_memory_proposal_lifecycle_uses_fake_store(monkeypatch):
    db = _ReflectionDb()
    proposal = _maintenance_proposal()
    db.row_by_id[proposal.id] = reflection._proposal_params(proposal)  # noqa: SLF001
    db.rows_by_table["reflection_proposals"] = [reflection._proposal_params(proposal)]  # noqa: SLF001
    events: list[tuple[str, str]] = []
    monkeypatch.setattr(reflection, "_database", lambda: db)
    monkeypatch.setattr(
        reflection,
        "_record_maintenance_event",
        lambda event_type, proposal: events.append((event_type, proposal.status)),
    )

    assert reflection.get_memory_maintenance_proposal("mp1").id == "mp1"
    assert [item.id for item in reflection.list_memory_maintenance_proposals("u1")] == ["mp1"]
    approved = reflection.approve_memory_maintenance_proposal("mp1", actor_user_id="u1")
    assert approved.status == "approved"
    rejected = reflection.reject_memory_maintenance_proposal("mp1", actor_user_id="u1")
    assert rejected.status == "rejected"
    expired = reflection.expire_memory_maintenance_proposal("mp1")
    assert expired.status == "expired"
    assert events == [
        ("memory_maintenance_proposal_approved", "approved"),
        ("memory_maintenance_proposal_rejected", "rejected"),
    ]

    with pytest.raises(PermissionError, match="owner"):
        reflection.approve_memory_maintenance_proposal("mp1", actor_user_id="other")
    with pytest.raises(ValueError, match="does not exist"):
        reflection.get_memory_maintenance_proposal("missing")


async def test_reflection_apply_memory_actions_and_guards(monkeypatch):
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def record(name: str, *args: Any) -> None:
        calls.append((name, args))

    monkeypatch.setattr(
        reflection.memory, "mark_user_memory_stale", lambda *args: record("stale", *args)
    )
    monkeypatch.setattr(
        reflection.memory,
        "update_user_memory_content",
        lambda *args: record("update", *args),
    )
    monkeypatch.setattr(
        reflection.memory, "merge_user_memories", lambda *args: record("merge", *args)
    )
    monkeypatch.setattr(
        reflection.memory, "delete_user_memory", lambda *args: record("delete", *args)
    )

    await reflection._apply_maintenance_action(  # noqa: SLF001
        _maintenance_proposal(action="mark_stale", target_memory_ids=["m1", "m2"])
    )
    await reflection._apply_maintenance_action(  # noqa: SLF001
        _maintenance_proposal(
            action="rewrite", target_memory_ids=["m3"], proposed_content=" revised "
        )
    )
    await reflection._apply_maintenance_action(  # noqa: SLF001
        _maintenance_proposal(
            action="compact", target_memory_ids=["m4"], proposed_content=" compacted "
        )
    )
    await reflection._apply_maintenance_action(  # noqa: SLF001
        _maintenance_proposal(
            action="merge", target_memory_ids=["m5", "m6"], proposed_content="merged"
        )
    )
    await reflection._apply_maintenance_action(  # noqa: SLF001
        _maintenance_proposal(action="delete", target_memory_ids=["m7"])
    )
    await reflection._apply_maintenance_action(  # noqa: SLF001
        _maintenance_proposal(action="suggest_agent_memory_or_kb", target_memory_ids=[])
    )
    assert calls == [
        ("stale", ("u1", "m1")),
        ("stale", ("u1", "m2")),
        ("update", ("u1", "m3", "revised")),
        ("update", ("u1", "m4", "compacted")),
        ("merge", ("u1", ["m5", "m6"], "merged")),
        ("delete", ("u1", "m7")),
    ]

    with pytest.raises(ValueError, match="proposed_content"):
        await reflection._apply_maintenance_action(  # noqa: SLF001
            _maintenance_proposal(action="rewrite", target_memory_ids=["m1"], proposed_content=" ")
        )
    with pytest.raises(ValueError, match="target_memory_ids"):
        await reflection._apply_maintenance_action(  # noqa: SLF001
            _maintenance_proposal(action="rewrite", target_memory_ids=[], proposed_content="x")
        )
    assert reflection._auto_apply_allowed(  # noqa: SLF001
        _maintenance_proposal(action="mark_stale", risk="low"),
        reflection.AutoMaintenancePolicy(allow_low_risk=True),
    )
    assert not reflection._auto_apply_allowed(  # noqa: SLF001
        _maintenance_proposal(action="suggest_agent_memory_or_kb", risk="low"),
        reflection.AutoMaintenancePolicy(allow_low_risk=True),
    )
    assert not reflection._auto_apply_allowed(  # noqa: SLF001
        _maintenance_proposal(action="delete", risk="low"),
        reflection.AutoMaintenancePolicy(allow_low_risk=True),
    )
    assert not reflection._auto_apply_allowed(  # noqa: SLF001
        _maintenance_proposal(action="merge", risk="low"),
        reflection.AutoMaintenancePolicy(allow_low_risk=True),
    )
    assert not reflection._auto_apply_allowed(  # noqa: SLF001
        _maintenance_proposal(action="rewrite", risk="low"),
        reflection.AutoMaintenancePolicy(allow_low_risk=True),
    )
    assert not reflection._auto_apply_allowed(  # noqa: SLF001
        _maintenance_proposal(action="compact", risk="low"),
        reflection.AutoMaintenancePolicy(allow_low_risk=True),
    )
    assert not reflection._auto_apply_allowed(  # noqa: SLF001
        _maintenance_proposal(action="mark_stale", risk="low"),
        None,
    )
    assert not reflection._auto_apply_allowed(  # noqa: SLF001
        _maintenance_proposal(action="mark_stale", risk="low"),
        reflection.AutoMaintenancePolicy(allow_low_risk=False),
    )
    with pytest.raises(ValueError, match="user_id"):
        reflection._validate_proposal_input(" ", "delete", "low", ["m1"])  # noqa: SLF001
    with pytest.raises(ValueError, match="unsupported maintenance action"):
        reflection._validate_proposal_input("u1", "noop", "low", [])  # type: ignore[arg-type]  # noqa: SLF001
    with pytest.raises(ValueError, match="unsupported maintenance risk"):
        reflection._validate_proposal_input("u1", "delete", "none", ["m1"])  # type: ignore[arg-type]  # noqa: SLF001
    with pytest.raises(ValueError, match="target_memory_ids"):
        reflection._validate_proposal_input("u1", "delete", "low", [])  # noqa: SLF001


async def test_reflection_apply_memory_proposal_full_flow(monkeypatch):
    updated: list[reflection.MemoryProposal] = []
    events: list[str] = []
    applied: list[str] = []
    proposal = _maintenance_proposal(status="approved", action="mark_stale", risk="low")

    monkeypatch.setattr(reflection, "get_memory_maintenance_proposal", lambda _id: proposal)
    monkeypatch.setattr(reflection, "_update_maintenance_proposal", updated.append)
    monkeypatch.setattr(
        reflection, "_record_maintenance_event", lambda event_type, _p: events.append(event_type)
    )

    async def fake_apply(p: reflection.MemoryProposal) -> None:
        applied.append(p.id)

    monkeypatch.setattr(reflection, "_apply_maintenance_action", fake_apply)

    result = await reflection.apply_memory_maintenance_proposal("mp1", actor_user_id="u1")
    assert result.status == "applied"
    assert updated[-1].status == "applied"
    assert applied == ["mp1"]
    assert events == ["memory_maintenance_proposal_applied"]

    expired = _maintenance_proposal(
        status="pending",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    monkeypatch.setattr(reflection, "get_memory_maintenance_proposal", lambda _id: expired)
    with pytest.raises(ValueError, match="cannot apply expired"):
        await reflection.apply_memory_maintenance_proposal("expired", actor_user_id="u1")

    pending = _maintenance_proposal(status="pending", risk="medium")
    monkeypatch.setattr(reflection, "get_memory_maintenance_proposal", lambda _id: pending)
    with pytest.raises(PermissionError, match="owner approval"):
        await reflection.apply_memory_maintenance_proposal("pending")


async def test_reflection_skill_proposal_lifecycle(monkeypatch):
    pending = _skill_proposal(status="pending")
    approved = _skill_proposal(status="approved")
    rejected = _skill_proposal(status="rejected")
    updated: list[reflection.SkillProposal] = []
    applied: list[str] = []
    default_apply_boundary = reflection.apply_skill_proposal_to_boundary

    monkeypatch.setattr(reflection, "_get_skill_proposal", lambda _id: pending)
    monkeypatch.setattr(reflection, "_update_skill_proposal", updated.append)
    assert reflection.get_skill_proposal("sp1").id == "sp1"
    assert (
        reflection.approve_skill_proposal("sp1", reviewer_user_id="reviewer").status == "approved"
    )
    assert reflection.reject_skill_proposal(
        "sp1", reviewer_user_id="reviewer", reason="no"
    ).status == ("rejected")
    with pytest.raises(ValueError, match="does not exist"):
        monkeypatch.setattr(reflection, "_get_skill_proposal", lambda _id: None)
        reflection.get_skill_proposal("missing")

    monkeypatch.setattr(reflection, "get_skill_proposal", lambda _id: rejected)
    with pytest.raises(ValueError, match="cannot apply rejected"):
        await reflection.apply_skill_proposal("sp1", actor_user_id="actor")

    monkeypatch.setattr(reflection, "get_skill_proposal", lambda _id: approved)

    async def fake_apply_boundary(proposal: reflection.SkillProposal) -> None:
        applied.append(proposal.id)

    monkeypatch.setattr(reflection, "apply_skill_proposal_to_boundary", fake_apply_boundary)
    result = await reflection.apply_skill_proposal("sp1", actor_user_id="actor")
    assert result.status == "applied"
    assert result.actor_user_id == "actor"
    assert applied == ["sp1"]

    import fleetent.skills as skills

    monkeypatch.setattr(
        skills,
        "write_skill",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("apply boundary failed")),
    )
    with pytest.raises(RuntimeError, match="apply boundary failed"):
        await default_apply_boundary(approved)


def test_reflection_list_skill_proposals_uses_fake_database(monkeypatch):
    db = _ReflectionDb()
    proposal = _skill_proposal()
    db.rows_by_table["reflection_proposals"] = [reflection._skill_proposal_params(proposal)]  # noqa: SLF001
    monkeypatch.setattr(reflection, "_database", lambda: db)

    assert [item.id for item in reflection.list_skill_proposals()] == ["sp1"]
    assert [item.id for item in reflection.list_skill_proposals(status=None)] == ["sp1"]

    db.tables.remove("reflection_proposals")
    assert reflection.list_skill_proposals() == []
