from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _patch_reflection_db(monkeypatch, tmp_path):
    from fleetent import reflection

    db_path = tmp_path / "reflection-mgmt.db"
    database = SQLiteDatabase(path=db_path)
    migrate(database, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(reflection, "_state_db", database)
    return database


def test_reflection_management_lists_skill_proposals_from_agent_store(monkeypatch, tmp_path):
    from fleetent import reflection
    from fleetent.platform import reflection_management
    from fleetent.reflection import ReflectionFinding

    _patch_reflection_db(monkeypatch, tmp_path)
    [proposal] = reflection.generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: triage inbox",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "triage inbox"},
            )
        ]
    )

    rows = reflection_management.reflection_list_proposals()
    assert any(r["id"] == proposal.id for r in rows)

    diff = reflection_management.reflection_proposal_diff(proposal.id)
    assert diff["proposal_id"] == proposal.id


def test_reflection_management_degrades_when_state_db_uninitialized(monkeypatch):
    """The per-agent reflection state_db is only wired in the agent process, never on the
    platform. Listing/diffing proposals from the platform console must therefore degrade to an
    empty inbox (so the frontend proposals tab renders) instead of raising the boot-time
    RuntimeError as a 500."""
    from fleetent import reflection
    from fleetent.platform import reflection_management

    monkeypatch.setattr(reflection, "_state_db", None)

    assert reflection_management.reflection_list_proposals() == []
    assert reflection_management.reflection_proposal_diff("any-id") == {
        "proposal_id": "any-id",
        "diff": "",
        "draft": "",
    }


def test_reflection_management_serializes_report_id(monkeypatch, tmp_path):
    from fleetent import reflection
    from fleetent.platform import reflection_management
    from fleetent.reflection import ReflectionFinding

    _patch_reflection_db(monkeypatch, tmp_path)
    [proposal] = reflection.generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: draft launch update",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "draft launch update"},
            )
        ],
        report_id="report-1",
    )

    [row] = [
        item
        for item in reflection_management.reflection_list_proposals()
        if item["id"] == proposal.id
    ]
    diff = reflection_management.reflection_proposal_diff(proposal.id)

    assert row["report_id"] == "report-1"
    assert diff["report_id"] == "report-1"


def test_skill_admin_api_consumes_reflection_management():
    from fleetent.platform import reflection_management
    from fleetent.platform.skill_management import skill_admin_api

    assert (
        skill_admin_api.reflection_list_proposals is reflection_management.reflection_list_proposals
    )
    assert (
        skill_admin_api.reflection_proposal_diff is reflection_management.reflection_proposal_diff
    )


def test_reflection_management_exposes_trend_summary_over_agent_store():
    from fleetent.platform import reflection_management

    assert hasattr(reflection_management, "get_reflection_trend_summary")
