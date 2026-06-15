from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from fleetent import reflection


class _Cursor:
    def __init__(self, *, rows=None, row=None) -> None:
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _FakeDb:
    def __init__(self, *, exists: bool = True, has_table: bool = True) -> None:
        self.path = SimpleNamespace(exists=lambda: exists)
        self.has_table = has_table
        self.rows: list[dict[str, object]] = []
        self.row: dict[str, object] | None = None
        self.executed: list[tuple[str, dict[str, object]]] = []

    def execute(self, sql: str, params: dict[str, object] | None = None) -> _Cursor:
        params = params or {}
        self.executed.append((sql, params))
        if "sqlite_master" in sql:
            name = str(params["name"])
            return _Cursor(row={"name": name} if self.has_table else None)
        if "fetchone" in sql:
            return _Cursor(row=self.row)
        if "WHERE id = :id" in sql:
            return _Cursor(row=self.row)
        rows = self.rows
        if "domain" in params:
            rows = [row for row in rows if row.get("domain") == params["domain"]]
        return _Cursor(rows=rows)


def _skill_row(
    *,
    id: str = "sp-1",
    kind: str = "create_skill",
    applied_at: str | None = None,
    status: str | None = None,
    report_id: str | None = None,
) -> dict[str, object]:
    payload = {"files": None, "suggested_draft": "draft", "suggested_diff": "diff"}
    return {
        "id": id,
        "domain": "skill",
        "kind": kind,
        "report_id": report_id,
        "subject_user_id": None,
        "target_ref": "triage-alerts",
        "payload_json": json.dumps(payload),
        "reason": "Repeated work",
        "evidence_json": json.dumps(["e1"]),
        "risk": "medium",
        "actor_user_id": None,
        "applied_at": applied_at,
        "created_at": "2026-06-15T00:00:00+00:00",
        "updated_at": "2026-06-15T00:00:00+00:00",
        "status": status,
    }


def _memory_row(
    *,
    id: str = "mp-1",
    kind: str = "mark_stale",
    applied_at: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    payload = {
        "target_memory_ids": ["m1"],
        "proposed_content": "updated",
        "metadata_patch": {"target": "shared_memory"},
    }
    return {
        "id": id,
        "domain": "memory",
        "kind": kind,
        "report_id": None,
        "subject_user_id": "user-1",
        "target_ref": None,
        "payload_json": json.dumps(payload),
        "reason": "Because",
        "evidence_json": json.dumps(["e1"]),
        "risk": "low",
        "actor_user_id": None,
        "applied_at": applied_at,
        "created_at": "2026-06-15T00:00:00+00:00",
        "updated_at": "2026-06-15T00:00:00+00:00",
        "status": status,
    }


def test_list_reflection_proposals_respects_missing_db_domain_and_status(monkeypatch) -> None:
    db = _FakeDb(exists=False)
    monkeypatch.setattr(reflection, "_database", lambda: db)
    assert reflection.list_reflection_proposals() == []

    db = _FakeDb(exists=True, has_table=False)
    monkeypatch.setattr(reflection, "_database", lambda: db)
    assert reflection.list_reflection_proposals() == []

    db = _FakeDb()
    db.rows = [
        _skill_row(id="sp-pending"),
        _skill_row(id="sp-applied", applied_at="2026-06-15T01:00:00+00:00"),
        _memory_row(id="mp-rejected", status="rejected"),
    ]
    monkeypatch.setattr(reflection, "_database", lambda: db)
    monkeypatch.setattr(reflection, "_approval_request_row", lambda proposal_id: None)

    pending = reflection.list_reflection_proposals(status="pending")
    all_records = reflection.list_reflection_proposals(status=None, domain="skill")

    assert [record.id for record in pending] == ["sp-pending"]
    assert [record.id for record in all_records] == ["sp-pending", "sp-applied"]


async def test_apply_skill_proposal_to_boundary_handles_create_update_deprecate_and_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    writes: list[tuple[str, dict[str, str], object]] = []
    monkeypatch.setattr(
        "fleetent.skills.write_skill",
        lambda name, files, provenance: writes.append((name, files, provenance)),
    )
    monkeypatch.setattr(
        reflection,
        "_load_existing_skill_bundle",
        lambda skill_name: {"SKILL.md": "---\nname: x\n---\nbody"},
    )
    monkeypatch.setattr(reflection, "_disable_skill_markdown", lambda content: "disabled")

    created = reflection.SkillProposal(
        id="sp-1",
        type="create_skill",
        target_skill="triage-alerts",
        reason="Repeated work",
        evidence_refs=["e1"],
        risk_level="medium",
        suggested_draft="draft-skill",
        suggested_diff=None,
        status="approved",
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
        updated_at=datetime(2026, 6, 15, tzinfo=UTC),
    )
    updated = reflection.SkillProposal(
        **{**created.__dict__, "id": "sp-2", "type": "update_skill", "files": {"notes.md": "n"}}
    )
    deprecated = reflection.SkillProposal(
        **{**created.__dict__, "id": "sp-3", "type": "deprecate_skill"}
    )

    with pytest.raises(ValueError, match="SKILL.md"):
        await reflection.apply_skill_proposal_to_boundary(
            reflection.SkillProposal(
                **{
                    **created.__dict__,
                    "id": "sp-err",
                    "suggested_draft": None,
                    "files": {"notes.md": "n"},
                }
            )
        )

    await reflection.apply_skill_proposal_to_boundary(created)
    await reflection.apply_skill_proposal_to_boundary(updated)
    await reflection.apply_skill_proposal_to_boundary(deprecated)

    assert writes[0][1]["SKILL.md"] == "draft-skill"
    assert writes[1][1]["SKILL.md"] == "draft-skill"
    assert writes[2][1]["SKILL.md"] == "disabled"


async def test_apply_skill_proposal_updates_actor_and_blocks_rejected(monkeypatch) -> None:
    proposal = reflection.SkillProposal(
        id="sp-1",
        type="create_skill",
        target_skill="triage-alerts",
        reason="Repeated work",
        evidence_refs=["e1"],
        risk_level="medium",
        suggested_draft="draft",
        suggested_diff=None,
        status="approved",
        created_at=datetime(2026, 6, 15, tzinfo=UTC),
        updated_at=datetime(2026, 6, 15, tzinfo=UTC),
    )
    updates: list[reflection.SkillProposal] = []
    monkeypatch.setattr(reflection, "get_skill_proposal", lambda proposal_id: proposal)
    monkeypatch.setattr(reflection, "apply_skill_proposal_to_boundary", AsyncMock())
    monkeypatch.setattr(
        reflection, "_update_skill_proposal", lambda updated: updates.append(updated)
    )

    result = await reflection.apply_skill_proposal("sp-1", actor_user_id="admin-1")
    assert result.status == "applied"
    assert result.actor_user_id == "admin-1"
    assert updates[-1].status == "applied"

    monkeypatch.setattr(
        reflection,
        "get_skill_proposal",
        lambda proposal_id: reflection.SkillProposal(**{**proposal.__dict__, "status": "rejected"}),
    )
    with pytest.raises(ValueError, match="rejected"):
        await reflection.apply_skill_proposal("sp-1", actor_user_id="admin-1")


def test_create_and_persist_memory_and_skill_proposals_fire_side_effects(monkeypatch) -> None:
    now = datetime(2026, 6, 15, tzinfo=UTC)
    created: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        reflection,
        "_insert_maintenance_proposal",
        lambda proposal: created.append(("insert_memory", proposal.id, proposal.status)),
    )
    monkeypatch.setattr(
        reflection,
        "_create_proposal_approval_request",
        lambda **kwargs: created.append(("approval", kwargs["proposal_id"], kwargs["domain"])),
    )
    monkeypatch.setattr(
        reflection,
        "_schedule_pending_proposal_notification",
        lambda **kwargs: created.append(("notify", kwargs["proposal_id"], kwargs["domain"])),
    )
    monkeypatch.setattr(
        reflection,
        "_record_maintenance_event",
        lambda event_type, proposal: created.append((event_type, proposal.id, proposal.status)),
    )
    monkeypatch.setattr("uuid.uuid4", lambda: SimpleNamespace(__str__=lambda self: "uuid-1"))
    monkeypatch.setattr(reflection, "datetime", SimpleNamespace(now=lambda tz=None: now, UTC=UTC))

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="user-1",
        action="mark_stale",
        target_memory_ids=["m1"],
        proposed_content="  keep  ",
        risk="low",
        reason="Because",
        evidence_ids=["e1"],
    )

    assert proposal.proposed_content == "keep"
    assert [entry[0] for entry in created] == [
        "insert_memory",
        "approval",
        "notify",
        "memory_maintenance_proposal_created",
    ]

    db = _FakeDb()
    monkeypatch.setattr(reflection, "_database", lambda: db)
    monkeypatch.setattr(reflection, "_has_table", lambda database, name: True)
    persisted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        reflection,
        "_insert_maintenance_proposal",
        lambda proposal: persisted.append(("memory", proposal.id)),
    )
    monkeypatch.setattr(
        reflection,
        "_insert_skill_proposal",
        lambda proposal: persisted.append(("skill", proposal.id)),
    )
    monkeypatch.setattr(
        reflection,
        "_create_proposal_approval_request",
        lambda **kwargs: persisted.append(("approval", kwargs["domain"])),
    )
    monkeypatch.setattr(
        reflection,
        "_schedule_pending_proposal_notification",
        lambda **kwargs: persisted.append(("notify", kwargs["domain"])),
    )
    monkeypatch.setattr(
        reflection,
        "_record_maintenance_event",
        lambda event_type, proposal: persisted.append(("event", proposal.id)),
    )

    reflection._persist_memory_maintenance_proposal(proposal)  # noqa: SLF001
    reflection._persist_skill_proposal(  # noqa: SLF001
        reflection.SkillProposal(
            id="sp-1",
            type="create_skill",
            target_skill="triage-alerts",
            reason="Repeated work",
            evidence_refs=["e1"],
            risk_level="medium",
            suggested_draft="draft",
            suggested_diff=None,
            status="pending",
            created_at=now,
            updated_at=now,
        )
    )
    assert persisted[:4] == [
        ("memory", proposal.id),
        ("approval", "memory"),
        ("notify", "memory"),
        ("event", proposal.id),
    ]
    assert persisted[-3:] == [("skill", "sp-1"), ("approval", "skill"), ("notify", "skill")]


def test_memory_and_skill_row_helpers_round_trip_and_status_helpers(monkeypatch) -> None:
    approval_rows = {
        "sp-1": {
            "status": "approved",
            "approver_user_id": "rev-1",
            "decided_at": "2026-06-15T01:00:00+00:00",
            "reason": "ok",
            "expires_at": "2026-06-16T00:00:00+00:00",
        },
        "mp-1": {"status": "expired", "expires_at": "2026-06-16T00:00:00+00:00"},
    }
    monkeypatch.setattr(
        reflection, "_approval_request_row", lambda proposal_id: approval_rows.get(str(proposal_id))
    )

    skill = reflection._skill_proposal_from_row(_skill_row())  # noqa: SLF001
    memory = reflection._proposal_from_row(_memory_row())  # noqa: SLF001

    assert skill.reviewer_user_id == "rev-1"
    assert skill.reviewed_at == datetime(2026, 6, 15, 1, 0, tzinfo=UTC)
    assert memory.expires_at == datetime(2026, 6, 16, tzinfo=UTC)
    assert reflection._proposal_status_for_row({"id": "missing", "applied_at": None}) == "pending"  # noqa: SLF001
    assert reflection._proposal_status_for_row({"id": "mp-1", "applied_at": None}) == "expired"  # noqa: SLF001


def test_misc_reflection_helpers_cover_status_validation_time_and_skill_bundle(
    monkeypatch, tmp_path: Path
) -> None:
    now = datetime(2026, 6, 15, tzinfo=UTC)
    proposal = reflection.MemoryMaintenanceProposal(
        id="mp-1",
        user_id="user-1",
        action="mark_stale",
        target_memory_ids=["m1"],
        proposed_content=" body ",
        metadata_patch={},
        risk="low",
        reason="Because",
        evidence_ids=["e1"],
        status="pending",
        created_at=now,
        updated_at=now,
        expires_at=None,
    )
    assert reflection._proposal_params(proposal)["subject_user_id"] == "user-1"  # noqa: SLF001
    assert reflection._skill_name("Triage Alerts Quickly!!!") == "triage-alerts-quickly"  # noqa: SLF001
    assert "Deterministic draft" in reflection._skill_draft("triage", "triage alerts", "Because")  # noqa: SLF001
    assert reflection._skill_diff("triage", "Because") == "Update 'triage': Because"  # noqa: SLF001
    assert reflection._int_signal({"n": 3.8}, "n") == 3  # noqa: SLF001
    assert reflection._real_skill_draft_enabled() is False  # noqa: SLF001

    monkeypatch.setenv("FLEETENT_REFLECTION_REAL_SKILL_DRAFT", "yes")
    assert reflection._real_skill_draft_enabled() is True  # noqa: SLF001
    assert reflection._parse_datetime("2026-06-15T00:00:00+00:00") == now  # noqa: SLF001
    assert reflection._parse_optional_datetime(None) is None  # noqa: SLF001
    assert reflection._format_datetime(now) == "2026-06-15T00:00:00+00:00"  # noqa: SLF001

    with pytest.raises(TypeError):
        reflection._parse_datetime(3)  # noqa: SLF001
    with pytest.raises(ValueError, match="must be pending"):
        reflection._require_skill_proposal_status(  # noqa: SLF001
            reflection.SkillProposal(
                id="sp-1",
                type="create_skill",
                target_skill="triage",
                reason="Repeated work",
                evidence_refs=["e1"],
                risk_level="medium",
                suggested_draft="draft",
                suggested_diff=None,
                status="approved",
                created_at=now,
                updated_at=now,
            ),
            {"pending"},
        )

    skills_root = tmp_path / "skills" / "triage"
    skills_root.mkdir(parents=True)
    (skills_root / "SKILL.md").write_text("---\nname: triage\n---\nbody", encoding="utf-8")
    (skills_root / "notes.md").write_text("notes", encoding="utf-8")
    monkeypatch.setattr("fleetent.skills.registry._last_skills_dir", str(tmp_path / "skills"))
    monkeypatch.setattr(
        "fleetent.skills.registry._resolve_skills_dir", lambda _value: str(tmp_path / "skills")
    )

    assert reflection._load_existing_skill_bundle("triage") == {  # noqa: SLF001
        "SKILL.md": "---\nname: triage\n---\nbody",
        "notes.md": "notes",
    }
    disabled = reflection._disable_skill_markdown("---\nname: triage\n---\nbody")  # noqa: SLF001
    assert "enabled: false" in disabled
