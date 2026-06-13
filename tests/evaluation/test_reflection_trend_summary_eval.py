import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration.test_migrations import apply_migrations

FIXTURE = Path("tests/evaluation/fixtures/reflection_trend_summary/basic.json")


def test_reflection_trend_summary_fixture_covers_direction_and_redaction(monkeypatch, tmp_path):
    from fleetent import reflection

    payload = json.loads(FIXTURE.read_text())
    db_path = tmp_path / "reflection-trend-eval.db"
    apply_migrations(db_path)
    database = SQLiteDatabase(path=db_path)
    migrate(database, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(reflection, "_state_db", database)

    with sqlite3.connect(db_path) as conn:
        for report in payload["reflection_reports"]:
            conn.execute(
                """
                INSERT INTO reflection_reports (
                    id, domain, scope, time_window_start, time_window_end, findings_json,
                    signal_summary_json, created_at
                )
                VALUES (?, 'memory', ?, ?, ?, ?, NULL, ?)
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
                INSERT INTO reflection_reports (
                    id, domain, scope, time_window_start, time_window_end, findings_json,
                    signal_summary_json, created_at
                )
                VALUES (?, 'knowledge_base', ?, ?, ?, ?, ?, ?)
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
                INSERT INTO reflection_proposals (
                    id, domain, kind, subject_user_id, target_ref, payload_json,
                    reason, evidence_json, risk, actor_user_id, applied_at, created_at, updated_at
                )
                VALUES (?, 'memory', ?, ?, NULL, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    proposal["id"],
                    proposal["action"],
                    payload["scope"],
                    json.dumps(
                        {
                            "target_memory_ids": proposal["target_memory_ids"],
                            "proposed_content": proposal["proposed_content"],
                            "metadata_patch": proposal["metadata_patch"],
                        }
                    ),
                    proposal["reason"],
                    json.dumps(proposal["evidence_ids"]),
                    proposal["risk"],
                    proposal.get("applied_at") or proposal["updated_at"],
                    proposal["created_at"],
                    proposal["updated_at"],
                ),
            )
        for proposal in payload["skill_proposals"]:
            conn.execute(
                """
                INSERT INTO reflection_proposals (
                    id, domain, kind, subject_user_id, target_ref, payload_json,
                    reason, evidence_json, risk, actor_user_id, applied_at, created_at, updated_at
                )
                VALUES (?, 'skill', ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    proposal["id"],
                    proposal["type"],
                    proposal["target_skill"],
                    json.dumps(
                        {
                            "files": None,
                            "suggested_draft": proposal.get("suggested_draft"),
                            "suggested_diff": proposal.get("suggested_diff"),
                        }
                    ),
                    proposal["reason"],
                    json.dumps(proposal["evidence_refs"]),
                    proposal["risk_level"],
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
