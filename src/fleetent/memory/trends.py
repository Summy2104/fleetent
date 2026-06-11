"""Read-only User Memory quality trend summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from fleetent.memory import proposal_store, shared, store


def _list_memory_maintenance_proposals(user_id: str) -> list[Any]:
    return proposal_store.list_memory_maintenance_proposals(user_id)


TrendBucketSize = Literal["day", "week"]


@dataclass(frozen=True)
class MemoryQualityTrendQuery:
    """Filter and bucket settings for a read-only memory quality summary."""

    user_id: str | None
    scope_type: str | None
    scope_id: str | None
    start_ts: datetime
    end_ts: datetime
    bucket: TrendBucketSize = "week"


@dataclass(frozen=True)
class MemoryQualityTrendBucket:
    """Aggregated memory quality counts for one time bucket."""

    start_ts: datetime
    end_ts: datetime
    user_memory_counts: dict[str, int]
    shared_memory_counts: dict[str, int]
    proposal_status_counts: dict[str, int]
    proposal_action_counts: dict[str, int]
    proposal_risk_counts: dict[str, int]
    expired_context_count: int
    duplicate_candidate_count: int


@dataclass(frozen=True)
class MemoryQualityTrendSummary:
    """Read-only memory quality trend result."""

    query: MemoryQualityTrendQuery
    buckets: list[MemoryQualityTrendBucket]


def get_memory_quality_trend_summary(
    query: MemoryQualityTrendQuery,
) -> MemoryQualityTrendSummary:
    """Return an on-demand memory quality trend summary without mutating memory state."""
    buckets = _build_empty_buckets(query)
    memory_rows = _memory_rows(query)
    for row in memory_rows:
        updated_at = store.parse_datetime(row["updated_at"])
        bucket = _bucket_for_timestamp(buckets, updated_at)
        if bucket is None:
            continue
        _increment(bucket.user_memory_counts, str(row["type"]))

        expires_at = store.parse_optional_datetime(row["expires_at"])
        if str(row["type"]) == "context" and expires_at is not None:
            expiry_bucket = _bucket_for_timestamp(buckets, expires_at)
            if expiry_bucket is not None:
                object.__setattr__(
                    expiry_bucket,
                    "expired_context_count",
                    expiry_bucket.expired_context_count + 1,
                )

    for index, count in _duplicate_candidate_counts(query, memory_rows).items():
        bucket = buckets[index]
        object.__setattr__(bucket, "duplicate_candidate_count", count)

    for row in _shared_memory_rows(query):
        updated_at = store.parse_datetime(row["updated_at"])
        bucket = _bucket_for_timestamp(buckets, updated_at)
        if bucket is not None:
            _increment(bucket.shared_memory_counts, str(row["type"]))

    for proposal in _memory_maintenance_proposals(query):
        bucket = _bucket_for_timestamp(buckets, proposal.updated_at)
        if bucket is None:
            continue
        _increment(bucket.proposal_status_counts, proposal.status)
        _increment(bucket.proposal_action_counts, proposal.action)
        _increment(bucket.proposal_risk_counts, proposal.risk)

    return MemoryQualityTrendSummary(query=query, buckets=buckets)


def _build_empty_buckets(query: MemoryQualityTrendQuery) -> list[MemoryQualityTrendBucket]:
    if query.end_ts <= query.start_ts:
        raise ValueError("end_ts must be after start_ts")
    if query.bucket not in {"day", "week"}:
        raise ValueError("bucket must be day or week")

    delta = timedelta(days=1 if query.bucket == "day" else 7)
    buckets: list[MemoryQualityTrendBucket] = []
    current = query.start_ts
    while current < query.end_ts:
        bucket_end = min(current + delta, query.end_ts)
        buckets.append(
            MemoryQualityTrendBucket(
                start_ts=current,
                end_ts=bucket_end,
                user_memory_counts={},
                shared_memory_counts={},
                proposal_status_counts={},
                proposal_action_counts={},
                proposal_risk_counts={},
                expired_context_count=0,
                duplicate_candidate_count=0,
            )
        )
        current = bucket_end
    return buckets


def _memory_rows(query: MemoryQualityTrendQuery) -> list[dict[str, Any]]:
    clauses = [
        "updated_at >= :start_ts",
        "updated_at < :end_ts",
    ]
    params: dict[str, object] = {
        "start_ts": store.format_datetime(query.start_ts),
        "end_ts": store.format_datetime(query.end_ts),
    }
    if query.user_id is not None:
        clauses.append("user_id = :user_id")
        params["user_id"] = query.user_id

    return (
        store.database()
        .execute(
            f"""
            SELECT id, user_id, type, content, created_at, updated_at, expires_at
            FROM memory_items
            WHERE {" AND ".join(clauses)}
            ORDER BY updated_at ASC, id ASC
            """,
            params,
        )
        .fetchall()
    )


def _duplicate_candidate_counts(
    query: MemoryQualityTrendQuery,
    rows: list[dict[str, Any]],
) -> dict[int, int]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row["type"]), store.normalize_memory_content(str(row["content"])))
        grouped.setdefault(key, []).append(row)

    counts: dict[int, int] = {}
    buckets = _build_empty_buckets(query)
    for duplicates in grouped.values():
        if len(duplicates) < 2:
            continue
        for row in duplicates[1:]:
            updated_at = store.parse_datetime(row["updated_at"])
            bucket_index = _bucket_index_for_timestamp(buckets, updated_at)
            if bucket_index is not None:
                counts[bucket_index] = counts.get(bucket_index, 0) + 1
    return counts


def _shared_memory_rows(query: MemoryQualityTrendQuery) -> list[dict[str, Any]]:
    clauses = [
        "updated_at >= :start_ts",
        "updated_at < :end_ts",
    ]
    params: dict[str, object] = {
        "start_ts": store.format_datetime(query.start_ts),
        "end_ts": store.format_datetime(query.end_ts),
    }
    if query.scope_type is not None:
        clauses.append("scope_type = :scope_type")
        params["scope_type"] = query.scope_type
    if query.scope_id is not None:
        clauses.append("scope_id = :scope_id")
        params["scope_id"] = query.scope_id

    return (
        shared._shared_memory_database()
        .execute(
            f"""
            SELECT id, scope_type, scope_id, type, status, updated_at
            FROM shared_memory_items
            WHERE {" AND ".join(clauses)}
            ORDER BY updated_at ASC, id ASC
            """,
            params,
        )
        .fetchall()
    )


def _memory_maintenance_proposals(query: MemoryQualityTrendQuery) -> list[Any]:
    if query.user_id is None:
        return []
    return [
        proposal
        for proposal in _list_memory_maintenance_proposals(query.user_id)
        if query.start_ts <= proposal.updated_at < query.end_ts
    ]


def _bucket_for_timestamp(
    buckets: list[MemoryQualityTrendBucket],
    timestamp: datetime,
) -> MemoryQualityTrendBucket | None:
    index = _bucket_index_for_timestamp(buckets, timestamp)
    if index is None:
        return None
    return buckets[index]


def _bucket_index_for_timestamp(
    buckets: list[MemoryQualityTrendBucket],
    timestamp: datetime,
) -> int | None:
    for index, bucket in enumerate(buckets):
        if bucket.start_ts <= timestamp < bucket.end_ts:
            return index
    return None


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1
