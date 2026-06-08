import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations

FIXTURE = Path("tests/evaluation/fixtures/reflection_trend_summary/basic.json")


def test_reflection_trend_summary_fixture_covers_direction_and_redaction(monkeypatch, tmp_path):
    from fleetent import reflection

    payload = json.loads(FIXTURE.read_text())
    db_path = tmp_path / "reflection-trend-eval.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(reflection, "_database", lambda: database)

    with sqlite3.connect(db_path) as conn:
        for report in payload["reflection_reports"]:
            conn.execute(
                """
                INSERT INTO reflection_reports (
                    id, scope, time_window_start, time_window_end, findings_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report["id"],
                    payload["scope"],
                    report["time_window_start"],
                    report["time_window_end"],
                    json.dumps(report["findings"]),
                    report["created_at"],
                ),
            )
        for report in payload["kb_reflection_reports"]:
            conn.execute(
                """
                INSERT INTO kb_reflection_reports (
                    id, scope, time_window_start, time_window_end, findings_json,
                    signal_summary_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report["id"],
                    payload["scope"],
                    report["time_window_start"],
                    report["time_window_end"],
                    json.dumps(report["findings"]),
                    json.dumps(report["signal_summary"]),
                    report["created_at"],
                ),
            )
        for proposal in payload["memory_maintenance_proposals"]:
            conn.execute(
                """
                INSERT INTO memory_maintenance_proposals (
                    id, user_id, action, target_memory_ids_json, proposed_content,
                    metadata_patch_json, risk, reason, evidence_ids_json, status,
                    created_at, updated_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal["id"],
                    payload["scope"],
                    proposal["action"],
                    json.dumps(proposal["target_memory_ids"]),
                    proposal["proposed_content"],
                    json.dumps(proposal["metadata_patch"]),
                    proposal["risk"],
                    proposal["reason"],
                    json.dumps(proposal["evidence_ids"]),
                    proposal["status"],
                    proposal["created_at"],
                    proposal["updated_at"],
                    proposal.get("expires_at"),
                ),
            )
        for proposal in payload["skill_proposals"]:
            conn.execute(
                """
                INSERT INTO skill_proposals (
                    id, type, target_skill, reason, evidence_refs_json, risk_level,
                    suggested_draft, suggested_diff, status, reviewer_user_id, reviewed_at,
                    rejection_reason, actor_user_id, applied_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal["id"],
                    proposal["type"],
                    proposal["target_skill"],
                    proposal["reason"],
                    json.dumps(proposal["evidence_refs"]),
                    proposal["risk_level"],
                    proposal.get("suggested_draft"),
                    proposal.get("suggested_diff"),
                    proposal["status"],
                    proposal.get("reviewer_user_id"),
                    proposal.get("reviewed_at"),
                    proposal.get("rejection_reason"),
                    proposal.get("actor_user_id"),
                    proposal.get("applied_at"),
                    proposal["created_at"],
                    proposal["updated_at"],
                ),
            )

    summary = reflection.get_reflection_trend_summary(
        reflection.ReflectionTrendQuery(
            scope=payload["scope"],
            start_ts=datetime.fromisoformat(payload["query"]["start_ts"]),
            end_ts=datetime.fromisoformat(payload["query"]["end_ts"]),
            bucket="week",
        )
    )

    missing_knowledge_counts = [
        bucket.finding_counts.get("missing_knowledge", 0) for bucket in summary.buckets
    ]
    memory_candidate_counts = [
        bucket.finding_counts.get("memory_candidate", 0) for bucket in summary.buckets
    ]
    assert missing_knowledge_counts == payload["expected"]["missing_knowledge_counts"]
    assert memory_candidate_counts == payload["expected"]["memory_candidate_counts"]
    assert missing_knowledge_counts[-1] > missing_knowledge_counts[0]
    assert memory_candidate_counts[-1] < memory_candidate_counts[0]
    assert "pending" not in summary.buckets[-1].proposal_status_counts
    assert payload["forbidden_transcript"] not in repr(summary)

    global_skill_summary = reflection.get_reflection_trend_summary(
        reflection.ReflectionTrendQuery(
            scope="global",
            start_ts=datetime.fromisoformat(payload["query"]["start_ts"]),
            end_ts=datetime.fromisoformat(payload["query"]["end_ts"]),
            bucket="week",
            domains=("skill",),
        )
    )
    assert global_skill_summary.buckets[-1].proposal_status_counts["pending"] == 2
