import json
from pathlib import Path

from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations

FIXTURE = Path("tests/evaluation/fixtures/skill_reflection_proposals/basic.json")


def test_skill_proposal_evaluation_fixture_covers_expected_and_forbidden_proposals(
    monkeypatch,
    tmp_path,
):
    from fleetent import reflection
    from fleetent.reflection import ReflectionFinding

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    db_path = tmp_path / "skill-proposals-eval.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(reflection, "_database", lambda: database)

    findings = [
        ReflectionFinding(
            type=item["type"],
            summary=item["summary"],
            evidence_ids=item["evidence_ids"],
            metadata=item["metadata"],
        )
        for item in payload["findings"]
    ]
    proposals = reflection.generate_skill_proposals(
        findings=findings,
        skill_signals=payload["skill_signals"],
    )
    actual = {(proposal.type, proposal.target_skill) for proposal in proposals}
    persisted = "\n".join(
        proposal.reason
        + "\n"
        + "\n".join(proposal.evidence_refs)
        + "\n"
        + (proposal.suggested_draft or "")
        + "\n"
        + (proposal.suggested_diff or "")
        for proposal in proposals
    )

    assert set(map(tuple, payload["expected_proposals"])) <= actual
    assert actual.isdisjoint(set(map(tuple, payload["forbidden_proposals"])))
    assert payload["forbidden_raw_text"] not in persisted
