from datetime import UTC, datetime, timedelta

from fleetent import memory
from fleetent.db import SQLiteDatabase, create_database
from fleetent.memory import store as memory_store
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration.test_migrations import apply_migrations


def test_memory_quality_trend_buckets_user_memory_counts_and_expired_context(
    tmp_path, monkeypatch
) -> None:
    database = _patch_database(tmp_path, monkeypatch)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    _insert_memory(
        database,
        id="identity-1",
        user_id="alice",
        type="identity",
        content="User is a platform engineer.",
        updated_at=start + timedelta(hours=1),
    )
    _insert_memory(
        database,
        id="preference-1",
        user_id="alice",
        type="preferences",
        content="User prefers concise replies.",
        updated_at=start + timedelta(days=1, hours=2),
    )
    _insert_memory(
        database,
        id="expired-context-1",
        user_id="alice",
        type="context",
        content="User is evaluating the migration plan.",
        updated_at=start + timedelta(days=1, hours=3),
        expires_at=start + timedelta(days=1, hours=4),
    )
    _insert_memory(
        database,
        id="other-user",
        user_id="bob",
        type="identity",
        content="Bob is outside this summary.",
        updated_at=start + timedelta(hours=1),
    )

    summary = memory.get_memory_quality_trend_summary(
        memory.MemoryQualityTrendQuery(
            user_id="alice",
            scope_type=None,
            scope_id=None,
            start_ts=start,
            end_ts=start + timedelta(days=2),
            bucket="day",
        )
    )

    assert [bucket.user_memory_counts for bucket in summary.buckets] == [
        {"identity": 1},
        {"context": 1, "preferences": 1},
    ]
    assert [bucket.expired_context_count for bucket in summary.buckets] == [0, 1]


def test_memory_quality_trend_keeps_shared_memory_counts_separate(tmp_path, monkeypatch) -> None:
    database = _patch_database(tmp_path, monkeypatch)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    _insert_memory(
        database,
        id="user-context",
        user_id="alice",
        type="context",
        content="User context remains per-user.",
        updated_at=start + timedelta(hours=1),
    )
    _insert_shared_memory(
        database,
        id="team-procedure",
        scope_type="team",
        scope_id="eng",
        type="procedure",
        content="Team deploys use the release checklist.",
        status="active",
        updated_at=start + timedelta(hours=2),
    )

    summary = memory.get_memory_quality_trend_summary(
        memory.MemoryQualityTrendQuery(
            user_id="alice",
            scope_type="team",
            scope_id="eng",
            start_ts=start,
            end_ts=start + timedelta(days=1),
            bucket="day",
        )
    )

    [bucket] = summary.buckets
    assert bucket.user_memory_counts == {"context": 1}
    assert bucket.shared_memory_counts == {"procedure": 1}


def test_memory_quality_trend_includes_maintenance_proposal_counts(tmp_path, monkeypatch) -> None:
    _patch_database(tmp_path, monkeypatch)
    from fleetent import reflection

    monkeypatch.setattr(reflection.observability, "record_trace_event", lambda event: None)
    pending = reflection.create_memory_maintenance_proposal(
        user_id="alice",
        action="delete",
        target_memory_ids=["mem-1"],
        proposed_content=None,
        risk="low",
        reason="Remove obsolete memory.",
        evidence_ids=["trace-1"],
    )
    approved = reflection.create_memory_maintenance_proposal(
        user_id="alice",
        action="rewrite",
        target_memory_ids=["mem-2"],
        proposed_content="User prefers Go.",
        risk="medium",
        reason="Clarify preference.",
        evidence_ids=["trace-2"],
    )
    rejected = reflection.create_memory_maintenance_proposal(
        user_id="alice",
        action="suggest_shared_memory_or_kb",
        target_memory_ids=[],
        proposed_content="Team uses GitHub Flow.",
        risk="high",
        reason="Shared candidate.",
        evidence_ids=["trace-3"],
    )
    reflection.approve_memory_maintenance_proposal(approved.id, actor_user_id="alice")
    reflection.reject_memory_maintenance_proposal(rejected.id, actor_user_id="alice")

    summary = memory.get_memory_quality_trend_summary(
        memory.MemoryQualityTrendQuery(
            user_id="alice",
            scope_type=None,
            scope_id=None,
            start_ts=pending.created_at - timedelta(seconds=1),
            end_ts=datetime.now(UTC) + timedelta(seconds=1),
            bucket="day",
        )
    )

    [bucket] = summary.buckets
    assert bucket.proposal_status_counts == {"approved": 1, "pending": 1, "rejected": 1}
    assert bucket.proposal_action_counts == {
        "delete": 1,
        "rewrite": 1,
        "suggest_shared_memory_or_kb": 1,
    }
    assert bucket.proposal_risk_counts == {"high": 1, "low": 1, "medium": 1}


def _patch_database(tmp_path, monkeypatch) -> SQLiteDatabase:
    from fleetent import reflection
    from fleetent.observability import traces

    db_path = tmp_path / "memory-quality-trends.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    db = create_database(f"sqlite:///{db_path}")
    migrate(db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(memory_store, "_state_db", db)
    # reflection no longer falls back to DATABASE_URL (agent-runtime-db-routing-cleanup):
    # inject its per-agent state DB explicitly.
    monkeypatch.setattr(reflection, "_state_db", db)
    monkeypatch.setattr(traces, "_state_db", db)
    return db


def _insert_memory(
    database: SQLiteDatabase,
    *,
    id: str,
    user_id: str,
    type: str,
    content: str,
    updated_at: datetime,
    expires_at: datetime | None = None,
) -> None:
    database.execute(
        """
        INSERT INTO memory_items (
            id, user_id, type, content, created_at, updated_at, expires_at
        )
        VALUES (
            :id, :user_id, :type, :content, :created_at, :updated_at, :expires_at
        )
        """,
        {
            "id": id,
            "user_id": user_id,
            "type": type,
            "content": content,
            "created_at": updated_at.isoformat(),
            "updated_at": updated_at.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at is not None else None,
        },
    )


def _insert_shared_memory(
    database: SQLiteDatabase,
    *,
    id: str,
    scope_type: str,
    scope_id: str,
    type: str,
    content: str,
    status: str,
    updated_at: datetime,
) -> None:
    database.execute(
        """
        INSERT INTO shared_memory_items (
            id, scope_type, scope_id, type, content, status, source, source_ref,
            created_by, created_at, updated_at
        )
        VALUES (
            :id, :scope_type, :scope_id, :type, :content, :status, :source, :source_ref,
            :created_by, :created_at, :updated_at
        )
        """,
        {
            "id": id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "type": type,
            "content": content,
            "status": status,
            "source": "manual",
            "source_ref": None,
            "created_by": "test",
            "created_at": updated_at.isoformat(),
            "updated_at": updated_at.isoformat(),
        },
    )
