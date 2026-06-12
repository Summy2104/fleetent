from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from fleetent import memory
from fleetent.db import SQLiteDatabase, create_database
from fleetent.memory import shared as shared_memory_store
from fleetent.memory.shared_memory_migrations import MIGRATIONS as SHARED_MEMORY_MIGRATIONS
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _patch_trend_db(monkeypatch, tmp_path):
    from fleetent.memory import store
    from tests.integration.test_migrations import apply_migrations

    db_path = tmp_path / "trends.db"
    shared_db_path = tmp_path / "shared.db"
    apply_migrations(db_path)
    migrate(SQLiteDatabase(path=db_path), AGENT_STATE_MIGRATIONS)
    shared_db = SQLiteDatabase(path=shared_db_path)
    migrate(shared_db, SHARED_MEMORY_MIGRATIONS)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(store, "database", lambda: database)
    monkeypatch.setattr(store, "_state_db", database)
    monkeypatch.setattr(shared_memory_store, "_shared_memory_db", shared_db)
    return database, shared_db


def _ts(day: int) -> datetime:
    return datetime(2026, 1, day, 12, 0, tzinfo=UTC)


def _fmt(value: datetime) -> str:
    from fleetent.memory import store

    return store.format_datetime(value)


def _insert_memory(item_id, user_id, type_, content, updated, expires=None):
    from fleetent.memory import store
    from fleetent.memory.models import MemoryItem

    store.insert_memory(
        MemoryItem(
            id=item_id,
            user_id=user_id,
            type=type_,
            content=content,
            created_at=updated,
            updated_at=updated,
            expires_at=expires,
        )
    )


def _insert_shared(database, item_id, type_, updated, scope_type="team", scope_id="eng"):
    database.execute(
        """
        INSERT INTO shared_memory_items
          (id, scope_type, scope_id, type, content, status, source,
           source_ref, created_by, created_at, updated_at)
        VALUES
          (:id, :scope_type, :scope_id, :type, 'c', 'active', 'manual',
           NULL, 'admin', :ts, :ts)
        """,
        {
            "id": item_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "type": type_,
            "ts": _fmt(updated),
        },
    )


def test_memory_quality_trend_public_api_is_importable() -> None:
    from fleetent.memory import (
        MemoryQualityTrendBucket,
        MemoryQualityTrendQuery,
        MemoryQualityTrendSummary,
        get_memory_quality_trend_summary,
    )

    assert MemoryQualityTrendQuery
    assert MemoryQualityTrendBucket
    assert MemoryQualityTrendSummary
    assert callable(get_memory_quality_trend_summary)
    assert memory.MemoryQualityTrendQuery is MemoryQualityTrendQuery


@pytest.mark.parametrize(
    ("start", "end", "bucket", "message"),
    [
        (_ts(5), _ts(5), "day", "end_ts must be after start_ts"),
        (_ts(1), _ts(5), "month", "bucket must be day or week"),
    ],
)
def test_build_empty_buckets_validates(start, end, bucket, message) -> None:
    query = memory.MemoryQualityTrendQuery(
        user_id=None, scope_type=None, scope_id=None, start_ts=start, end_ts=end, bucket=bucket
    )
    with pytest.raises(ValueError, match=message):
        memory.get_memory_quality_trend_summary(query)


def _no_proposals(monkeypatch) -> None:
    monkeypatch.setattr(
        "fleetent.memory.trends._list_memory_maintenance_proposals", lambda user_id: []
    )


def test_daily_buckets_count_user_memories_and_expiry(monkeypatch, tmp_path) -> None:
    _patch_trend_db(monkeypatch, tmp_path)
    _no_proposals(monkeypatch)
    _insert_memory("m1", "u1", "identity", "alice", _ts(1))
    _insert_memory("m2", "u1", "identity", "bob", _ts(1))
    _insert_memory("m3", "u1", "preferences", "dark mode", _ts(2))
    # context row updated day 1 that expires day 3 -> expiry recorded in day-3 bucket
    _insert_memory("m4", "u1", "context", "ctx", _ts(1), expires=_ts(3))
    # a different user's row must be excluded by the user_id filter
    _insert_memory("x1", "u2", "identity", "carol", _ts(1))

    query = memory.MemoryQualityTrendQuery(
        user_id="u1",
        scope_type=None,
        scope_id=None,
        start_ts=_ts(1),
        end_ts=_ts(4),
        bucket="day",
    )
    summary = memory.get_memory_quality_trend_summary(query)

    assert len(summary.buckets) == 3
    day1, day2, day3 = summary.buckets
    assert day1.user_memory_counts == {"identity": 2, "context": 1}
    assert day2.user_memory_counts == {"preferences": 1}
    assert day3.expired_context_count == 1
    assert day1.expired_context_count == 0


def test_duplicate_candidate_counts(monkeypatch, tmp_path) -> None:
    _patch_trend_db(monkeypatch, tmp_path)
    _no_proposals(monkeypatch)
    # three same-content identity rows -> 2 duplicates beyond the canonical one
    _insert_memory("d1", "u1", "identity", "Same Fact", _ts(1))
    _insert_memory("d2", "u1", "identity", "same fact", _ts(1))
    _insert_memory("d3", "u1", "identity", "SAME FACT", _ts(2))

    query = memory.MemoryQualityTrendQuery(
        user_id="u1",
        scope_type=None,
        scope_id=None,
        start_ts=_ts(1),
        end_ts=_ts(4),
        bucket="day",
    )
    summary = memory.get_memory_quality_trend_summary(query)

    assert sum(b.duplicate_candidate_count for b in summary.buckets) == 2


def test_shared_memory_and_weekly_bucketing(monkeypatch, tmp_path) -> None:
    _, shared_database = _patch_trend_db(monkeypatch, tmp_path)
    _insert_shared(shared_database, "s1", "context", _ts(1))
    _insert_shared(shared_database, "s2", "procedure", _ts(2))
    # scope filter must exclude this one
    _insert_shared(shared_database, "s3", "context", _ts(2), scope_id="other")

    query = memory.MemoryQualityTrendQuery(
        user_id=None,
        scope_type="team",
        scope_id="eng",
        start_ts=_ts(1),
        end_ts=_ts(8),
        bucket="week",
    )
    summary = memory.get_memory_quality_trend_summary(query)

    assert len(summary.buckets) == 1
    assert summary.buckets[0].shared_memory_counts == {"context": 1, "procedure": 1}


def test_maintenance_proposals_counted(monkeypatch, tmp_path) -> None:
    _patch_trend_db(monkeypatch, tmp_path)

    @dataclass(frozen=True)
    class _Proposal:
        updated_at: datetime
        status: str
        action: str
        risk: str

    proposals = [
        _Proposal(_ts(1), "pending", "delete", "low"),
        _Proposal(_ts(1), "approved", "merge", "medium"),
        # far outside the window -> ignored
        _Proposal(datetime(2026, 2, 1, tzinfo=UTC), "pending", "delete", "low"),
    ]
    monkeypatch.setattr(
        "fleetent.memory.trends._list_memory_maintenance_proposals", lambda user_id: proposals
    )

    query = memory.MemoryQualityTrendQuery(
        user_id="u1",
        scope_type=None,
        scope_id=None,
        start_ts=_ts(1),
        end_ts=_ts(4),
        bucket="day",
    )
    summary = memory.get_memory_quality_trend_summary(query)

    day1 = summary.buckets[0]
    assert day1.proposal_status_counts == {"pending": 1, "approved": 1}
    assert day1.proposal_action_counts == {"delete": 1, "merge": 1}
    assert day1.proposal_risk_counts == {"low": 1, "medium": 1}


def test_proposals_skipped_without_user(monkeypatch, tmp_path) -> None:
    _patch_trend_db(monkeypatch, tmp_path)
    query = memory.MemoryQualityTrendQuery(
        user_id=None,
        scope_type=None,
        scope_id=None,
        start_ts=_ts(1),
        end_ts=_ts(4),
        bucket="day",
    )
    summary = memory.get_memory_quality_trend_summary(query)
    assert all(b.proposal_status_counts == {} for b in summary.buckets)
