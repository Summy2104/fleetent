import json
import sqlite3
from datetime import UTC, datetime

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration.test_migrations import apply_migrations


def _patch_reflection_db(monkeypatch, tmp_path):
    from fleetent import reflection

    db_path = tmp_path / "reflection-trends.db"
    database = SQLiteDatabase(path=db_path)
    apply_migrations(db_path)
    migrate(database, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(reflection, "_state_db", database)
    return db_path


def test_reflection_trend_summary_buckets_report_findings(monkeypatch, tmp_path):
    from fleetent.reflection import (
        ReflectionTrendQuery,
        get_reflection_trend_summary,
    )

    db_path = _patch_reflection_db(monkeypatch, tmp_path)
    forbidden_transcript = "raw customer transcript should stay hidden"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO reflection_reports (
                id, domain, scope, time_window_start, time_window_end, findings_json,
                signal_summary_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "report-1",
                "memory",
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
                None,
                "2026-01-01T01:00:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO reflection_reports (
                id, domain, scope, time_window_start, time_window_end, findings_json,
                signal_summary_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "kb-report-1",
                "knowledge_base",
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
    from fleetent.reflection import (
        ReflectionTrendQuery,
        get_reflection_trend_summary,
    )

    db_path = _patch_reflection_db(monkeypatch, tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO reflection_proposals (
                id, domain, kind, subject_user_id, target_ref, payload_json,
                reason, evidence_json, risk, status, reviewer_user_id,
                reviewed_at, rejection_reason, actor_user_id, applied_at,
                expires_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "memory-proposal-1",
                "memory",
                "rewrite",
                "owner-1",
                None,
                json.dumps(
                    {
                        "target_memory_ids": ["mem-1"],
                        "proposed_content": "redacted content",
                        "metadata_patch": {},
                    }
                ),
                "aggregate only",
                json.dumps(["trace-1"]),
                "medium",
                "applied",
                None,
                None,
                None,
                None,
                None,
                None,
                "2026-01-01T02:00:00+00:00",
                "2026-01-01T02:10:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO reflection_proposals (
                id, domain, kind, subject_user_id, target_ref, payload_json,
                reason, evidence_json, risk, status, reviewer_user_id,
                reviewed_at, rejection_reason, actor_user_id, applied_at,
                expires_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "memory-proposal-2",
                "memory",
                "delete",
                "owner-1",
                None,
                json.dumps(
                    {
                        "target_memory_ids": ["mem-2"],
                        "proposed_content": None,
                        "metadata_patch": {},
                    }
                ),
                "aggregate only",
                json.dumps(["trace-2"]),
                "high",
                "rejected",
                None,
                None,
                None,
                None,
                None,
                None,
                "2026-01-01T03:00:00+00:00",
                "2026-01-01T03:10:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO reflection_proposals (
                id, domain, kind, subject_user_id, target_ref, payload_json,
                reason, evidence_json, risk, status, reviewer_user_id,
                reviewed_at, rejection_reason, actor_user_id, applied_at,
                expires_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "skill-proposal-1",
                "skill",
                "update_skill",
                None,
                "incident-runbook",
                json.dumps({"files": None, "suggested_draft": None, "suggested_diff": "--- diff"}),
                "aggregate only",
                json.dumps(["trace-3"]),
                "low",
                "pending",
                None,
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
