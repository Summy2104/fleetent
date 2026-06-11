from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _patch_reflection_db(monkeypatch, tmp_path):
    from fleetent import reflection

    db_path = tmp_path / "skill-proposals.db"
    database = SQLiteDatabase(path=db_path)
    migrate(database, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(reflection, "_state_db", database)
    return database


def test_skill_proposal_persistence_redacts_raw_transcript(monkeypatch, tmp_path):
    from fleetent import reflection
    from fleetent.reflection import ReflectionFinding

    database = _patch_reflection_db(monkeypatch, tmp_path)
    raw_transcript = "RAW TRANSCRIPT SHOULD NOT BE STORED"
    [proposal] = reflection.generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: summarize launch notes",
                evidence_ids=["trace-a", "trace-b"],
                metadata={
                    "pattern": "summarize launch notes",
                    "transcript": raw_transcript,
                },
            )
        ]
    )

    row = database.execute(
        """
        SELECT reason, evidence_json, payload_json
        FROM reflection_proposals
        WHERE id = :id
        """,
        {"id": proposal.id},
    ).fetchone()

    assert row is not None
    persisted = row["reason"] + row["evidence_json"] + row["payload_json"]
    assert "summarize launch notes" in persisted
    assert "trace-a" in persisted
    assert raw_transcript not in persisted


async def test_apply_skill_proposal_updates_state_after_boundary(monkeypatch, tmp_path):
    from fleetent import reflection
    from fleetent.reflection import ReflectionFinding

    _patch_reflection_db(monkeypatch, tmp_path)
    calls: list[str] = []

    async def apply_boundary(proposal):
        calls.append(proposal.target_skill)

    monkeypatch.setattr(reflection, "apply_skill_proposal_to_boundary", apply_boundary)
    [proposal] = reflection.generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: prepare release notes",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "prepare release notes"},
            )
        ]
    )
    reflection.approve_skill_proposal(proposal.id, reviewer_user_id="reviewer")

    applied = await reflection.apply_skill_proposal(proposal.id, actor_user_id="admin")
    loaded = reflection.get_skill_proposal(proposal.id)

    assert calls == ["prepare-release-notes"]
    assert applied.status == "applied"
    assert loaded.status == "applied"
    assert loaded.applied_at is not None
    assert loaded.actor_user_id == "admin"
