# Design

## Evaluation Result

可以进入设计。依据：

- `reflection_reports` 已保存 foundation findings 且不包含 raw transcript。
- `kb_reflection_reports` 已保存 KB 质量 findings 和 signal summary。
- `memory_maintenance_proposals` 与 `skill_proposals` 已有 pending / approved / rejected / applied 状态。
- 所有输入都属于 reflection-owned 表或 reflection public API，不需要跨模块读取 internal 实现。

## Data Sources

第一版趋势汇总只读以下数据：

- `reflection_reports.findings_json`
- `kb_reflection_reports.findings_json`
- `kb_reflection_reports.signal_summary_json`
- `memory_maintenance_proposals.status` / `risk` / `action` / timestamps
- `skill_proposals.status` / `risk_level` / `type` / timestamps

## Public API Shape

```python
@dataclass(frozen=True)
class ReflectionTrendQuery:
    scope: str
    start_ts: datetime
    end_ts: datetime
    bucket: Literal["day", "week"] = "week"
    domains: tuple[Literal["memory", "knowledge_base", "skill"], ...] = (...)


@dataclass(frozen=True)
class ReflectionTrendBucket:
    start_ts: datetime
    end_ts: datetime
    finding_counts: dict[str, int]
    proposal_status_counts: dict[str, int]
    applied_count: int
    rejected_count: int


@dataclass(frozen=True)
class ReflectionTrendSummary:
    query: ReflectionTrendQuery
    buckets: list[ReflectionTrendBucket]
    top_findings: list[str]
```

## Rules

- Bucket boundaries are deterministic UTC day/week ranges.
- Finding type names are preserved as stored; unknown future types are counted, not rejected.
- Proposal apply/reject ratios are calculated only when denominator > 0; otherwise omitted.
- Trend summary must not expose evidence payloads beyond ids and aggregate counts.

## Evaluation

Add deterministic fixtures with synthetic reports/proposals:

- increasing `missing_knowledge` over two buckets;
- declining `memory_candidate` after proposal apply;
- skill proposal pending backlog;
- forbidden raw transcript snippets absent from output.

## Open Questions

- UI ownership remains open; this spec only provides API/evaluation.
- Scheduler cadence remains open; first implementation should be on-demand query only.
