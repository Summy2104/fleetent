import json
import sqlite3
from datetime import UTC, datetime

from fleetent.db import create_database
from tests.integration.test_migrations import apply_migrations


def _patch_reflection_db(monkeypatch, tmp_path):
    from fleetent.intelligence import reflection

    db_path = tmp_path / "reflection-trends.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(reflection, "_database", lambda: database)
    return db_path


def test_reflection_trend_summary_buckets_report_findings(monkeypatch, tmp_path):
    from fleetent.intelligence.reflection import (
        ReflectionTrendQuery,
        get_reflection_trend_summary,
    )

    db_path = _patch_reflection_db(monkeypatch, tmp_path)
    forbidden_transcript = "raw customer transcript should stay hidden"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO reflection_reports (
                id, scope, time_window_start, time_window_end, findings_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "report-1",
                "owner-1",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T01:00:00+00:00",
                json.dumps(
                    [
                        {
                            "type": "memory_candidate",
                            "summary": forbidden_transcript,
                            "evidence_ids": ["trace-1"],
                            "metadata": {"future": "kept"},
                        },
                        {
                            "type": "future_reflection_signal",
                            "summary": "unknown type",
                            "evidence_ids": ["trace-2"],
                            "metadata": {},
                        },
                    ]
                ),
                "2026-01-01T01:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO kb_reflection_reports (
                id, scope, time_window_start, time_window_end, findings_json,
                signal_summary_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "kb-report-1",
                "owner-1",
                "2026-01-02T00:00:00+00:00",
                "2026-01-02T01:00:00+00:00",
                json.dumps(
                    [
                        {
                            "type": "missing_knowledge",
                            "severity": "high",
                            "affected_resource": "kb:article",
                            "evidence_refs": ["trace-3"],
                            "recommendation": forbidden_transcript,
                            "metadata": {},
                        }
                    ]
                ),
                json.dumps({"query_count": 1}),
                "2026-01-02T01:00:00+00:00",
            ),
        )

    summary = get_reflection_trend_summary(
        ReflectionTrendQuery(
            scope="owner-1",
            start_ts=datetime(2026, 1, 1, tzinfo=UTC),
            end_ts=datetime(2026, 1, 3, tzinfo=UTC),
            bucket="day",
            domains=("memory", "knowledge_base"),
        )
    )

    assert [bucket.finding_counts for bucket in summary.buckets] == [
        {"memory_candidate": 1, "future_reflection_signal": 1},
        {"missing_knowledge": 1},
    ]
    assert summary.top_findings == [
        "future_reflection_signal",
        "memory_candidate",
        "missing_knowledge",
    ]
    assert forbidden_transcript not in repr(summary)


def test_reflection_trend_summary_buckets_scoped_memory_proposal_lifecycle(monkeypatch, tmp_path):
    from fleetent.intelligence.reflection import (
        ReflectionTrendQuery,
        get_reflection_trend_summary,
    )

    db_path = _patch_reflection_db(monkeypatch, tmp_path)
    with sqlite3.connect(db_path) as conn:
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
                "memory-proposal-1",
                "owner-1",
                "rewrite",
                json.dumps(["mem-1"]),
                "redacted content",
                json.dumps({}),
                "medium",
                "aggregate only",
                json.dumps(["trace-1"]),
                "applied",
                "2026-01-01T02:00:00+00:00",
                "2026-01-01T02:10:00+00:00",
                None,
            ),
        )
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
                "memory-proposal-2",
                "owner-1",
                "delete",
                json.dumps(["mem-2"]),
                None,
                json.dumps({}),
                "high",
                "aggregate only",
                json.dumps(["trace-2"]),
                "rejected",
                "2026-01-01T03:00:00+00:00",
                "2026-01-01T03:10:00+00:00",
                None,
            ),
        )
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
                "skill-proposal-1",
                "update_skill",
                "incident-runbook",
                "aggregate only",
                json.dumps(["trace-3"]),
                "low",
                None,
                "--- diff",
                "pending",
                None,
                None,
                None,
                None,
                None,
                "2026-01-01T04:00:00+00:00",
                "2026-01-01T04:10:00+00:00",
            ),
        )

    [bucket] = get_reflection_trend_summary(
        ReflectionTrendQuery(
            scope="owner-1",
            start_ts=datetime(2026, 1, 1, tzinfo=UTC),
            end_ts=datetime(2026, 1, 2, tzinfo=UTC),
            bucket="day",
            domains=("memory", "skill"),
        )
    ).buckets

    assert bucket.proposal_status_counts == {
        "applied": 1,
        "rejected": 1,
    }
    assert bucket.proposal_risk_counts == {"high": 1, "medium": 1}
    assert bucket.proposal_action_counts == {"delete": 1, "rewrite": 1}
    assert bucket.proposal_type_counts == {}
    assert bucket.applied_count == 1
    assert bucket.rejected_count == 1
    assert bucket.applied_ratio == 1 / 2
    assert bucket.rejected_ratio == 1 / 2

    [global_bucket] = get_reflection_trend_summary(
        ReflectionTrendQuery(
            scope="global",
            start_ts=datetime(2026, 1, 1, tzinfo=UTC),
            end_ts=datetime(2026, 1, 2, tzinfo=UTC),
            bucket="day",
            domains=("skill",),
        )
    ).buckets

    assert global_bucket.proposal_status_counts == {"pending": 1}
    assert global_bucket.proposal_risk_counts == {"low": 1}
    assert global_bucket.proposal_action_counts == {}
    assert global_bucket.proposal_type_counts == {"update_skill": 1}
    assert global_bucket.applied_count == 0
    assert global_bucket.rejected_count == 0
    assert global_bucket.applied_ratio == 0
    assert global_bucket.rejected_ratio == 0
