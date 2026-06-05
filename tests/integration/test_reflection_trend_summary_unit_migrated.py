def test_reflection_trend_summary_public_api_is_importable():
    from fleetent.intelligence.reflection import (
        ReflectionTrendBucket,
        ReflectionTrendQuery,
        ReflectionTrendSummary,
        get_reflection_trend_summary,
    )

    assert ReflectionTrendQuery is not None
    assert ReflectionTrendBucket is not None
    assert ReflectionTrendSummary is not None
    assert callable(get_reflection_trend_summary)


def test_skill_proposals_are_only_counted_for_global_scope(monkeypatch, tmp_path):
    from datetime import UTC, datetime, timedelta

    from fleetent.db import create_database
    from fleetent.intelligence import reflection
    from tests.integration.test_migrations import apply_migrations

    db_path = tmp_path / "reflection-trend-scope.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(reflection, "_database", lambda: database)

    now = datetime.now(UTC).replace(microsecond=0)
    reflection.generate_skill_proposals(
        findings=[
            reflection.ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated deployment checklist task",
                evidence_ids=["trace-1", "trace-2"],
                metadata={"pattern": "deployment checklist"},
            )
        ]
    )

    scoped = reflection.get_reflection_trend_summary(
        reflection.ReflectionTrendQuery(
            scope="tenant-a",
            start_ts=now - timedelta(days=1),
            end_ts=now + timedelta(days=1),
            bucket="week",
            domains=("skill",),
        )
    )
    global_summary = reflection.get_reflection_trend_summary(
        reflection.ReflectionTrendQuery(
            scope="global",
            start_ts=now - timedelta(days=1),
            end_ts=now + timedelta(days=1),
            bucket="week",
            domains=("skill",),
        )
    )

    assert scoped.buckets[0].proposal_type_counts == {}
    assert global_summary.buckets[0].proposal_type_counts == {"create_skill": 1}
