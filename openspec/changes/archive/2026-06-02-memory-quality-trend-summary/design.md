# Design

## Evaluation Result

可以进入设计。依据：

- `memory_items` 和 `shared_memory_items` 已有稳定 schema。
- `run_memory_maintenance(dry_run=True)` 可以暴露 expired / over-limit / duplicate exact-match signals。
- reflection 的 memory maintenance proposal lifecycle 已能统计 pending / approved / rejected / applied。
- memory extraction evaluation 已有 deterministic fixture，可作为质量基线来源。

## Data Sources

- `memory_items`：按 user/type/status-like TTL 聚合。
- `shared_memory_items`：按 scope/type/status 聚合。
- `memory_maintenance_proposals`：按 action/risk/status 聚合。
- Optional evaluation fixture summaries：只读读取 deterministic evaluation output，不触发真实 LLM。

## Public API Shape

```python
@dataclass(frozen=True)
class MemoryQualityTrendQuery:
    user_id: str | None
    scope_type: str | None
    scope_id: str | None
    start_ts: datetime
    end_ts: datetime
    bucket: Literal["day", "week"] = "week"


@dataclass(frozen=True)
class MemoryQualityTrendBucket:
    start_ts: datetime
    end_ts: datetime
    user_memory_counts: dict[str, int]
    shared_memory_counts: dict[str, int]
    proposal_status_counts: dict[str, int]
    expired_context_count: int
    duplicate_candidate_count: int


@dataclass(frozen=True)
class MemoryQualityTrendSummary:
    query: MemoryQualityTrendQuery
    buckets: list[MemoryQualityTrendBucket]
```

## Rules

- Summary is read-only and on-demand.
- User Memory and Shared Memory are reported separately; Shared Memory must not be mixed into per-user counts.
- Duplicate candidate counting uses the existing exact duplicate policy, not semantic similarity.
- Evaluation results are optional metadata; missing evaluation records do not fail the trend query.

## Open Questions

- Whether evaluation history should be persisted is not decided. First implementation may aggregate only database state and leave evaluation trend as fixture-only.
- UI ownership remains out of scope.
