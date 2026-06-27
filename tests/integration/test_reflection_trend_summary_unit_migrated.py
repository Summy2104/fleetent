def test_reflection_trend_summary_public_api_is_importable():
    from fleetent.reflection import (
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

    from fleetent import reflection
    from fleetent.db import create_database
    from fleetent.governance import approval_request_store
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.schema_migrations import migrate
    from tests.integration.test_migrations import apply_migrations

    db_path = tmp_path / "reflection-trend-scope.db"
    apply_migrations(db_path)
    migrate(create_database(f"sqlite:///{db_path}"), AGENT_STATE_MIGRATIONS)
    database = create_database(f"sqlite:///{db_path}")
    # Wire both globals that reflection.set_state_db() wires at boot: persisting a
    # skill proposal also creates an approval request via approval_request_store.
    # Patching only reflection's db left approval_request_store._state_db unset, so
    # the test silently relied on a prior test on the same worker leaking it —
    # order-dependent RuntimeError otherwise. monkeypatch auto-restores both.
    monkeypatch.setattr(reflection, "_state_db", database)
    monkeypatch.setattr(approval_request_store, "_state_db", database)

    now = datetime.now(UTC).replace(microsecond=0)
    for proposal in reflection.generate_skill_proposals(
        findings=[
            reflection.ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated deployment checklist task",
                evidence_ids=["trace-1", "trace-2"],
                metadata={"pattern": "deployment checklist"},
            )
        ]
    ):
        reflection._persist_skill_proposal(proposal)

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
