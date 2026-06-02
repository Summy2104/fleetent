## Overview

本 change 提供 observability usage summary 的第一版：从 SQLite agent traces 中读取
`agent_run_completed` event，并实时聚合调用次数、token 用量和耗时。它是 platform dashboard、
quota 和后续成本分析的基础，但本身不做 UI、不做预算控制、不做 rollup 持久化。

## Public API

```python
@dataclass(frozen=True)
class UsageQuery:
    user_id: str | None = None
    agent_id: str | None = None
    tenant_id: str | None = None
    session_id: str | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    limit: int = 10_000


@dataclass(frozen=True)
class ModelUsage:
    model: str
    run_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_elapsed_s: float
    avg_elapsed_s: float


@dataclass(frozen=True)
class UsageSummary:
    run_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_elapsed_s: float
    avg_elapsed_s: float
    by_model: list[ModelUsage]


def get_usage_summary(query: UsageQuery) -> UsageSummary:
    """Return usage aggregates from agent_run_completed trace events."""
```

## Source Data

只读取 `event_type="agent_run_completed"` 的 trace events。

字段来源：

- `TraceEvent.user_id`
- `TraceEvent.agent_id`
- `TraceEvent.tenant_id`
- `TraceEvent.session_id`
- `TraceEvent.ts`
- `TraceEvent.payload["tokens"]`
- `TraceEvent.payload["elapsed_s"]`
- `TraceEvent.payload["model_used"]`

payload 字段缺失或类型非法时，按 0 或 `"unknown"` 处理，不抛错。

## Query Behavior

`get_usage_summary()` 应通过 `query_trace_events()` 查询，而不是直接 SQL 访问 `traces` 表。

过滤映射：

- `user_id` → `TraceQuery.user_id`
- `agent_id` → `TraceQuery.agent_id`
- `tenant_id` → `TraceQuery.tenant_id`
- `start_ts` → `TraceQuery.start_ts`
- `end_ts` → `TraceQuery.end_ts`
- `event_type` 固定为 `agent_run_completed`
- `limit` → `TraceQuery.limit`

`session_id` 如果 `TraceQuery` 支持顶层过滤则传入；如果当前 TraceQuery 尚未支持 session 过滤，则在
usage summary 层读取后内存过滤。本 change 不要求修改 traces schema。

## Aggregation Rules

每个 `agent_run_completed` event 计为一次 run。

tokens 读取规则：

```python
tokens = payload.get("tokens") or {}
prompt = int(tokens.get("prompt", 0) or 0)
completion = int(tokens.get("completion", 0) or 0)
total = int(tokens.get("total", prompt + completion) or 0)
```

elapsed 读取规则：

```python
elapsed_s = float(payload.get("elapsed_s", 0) or 0)
```

model 读取规则：

```python
model = payload.get("model_used") or "unknown"
```

`avg_elapsed_s = total_elapsed_s / run_count`；run_count 为 0 时 avg 为 0。

`by_model` 按 `total_tokens` 降序，total_tokens 相同时按 model 升序稳定排序。

## Error Handling

- 缺失 tokens：按 0 处理。
- 缺失 elapsed_s：按 0 处理。
- 非数字 token / elapsed：按 0 处理。
- 缺失 model_used：归入 `"unknown"`。
- `query_trace_events()` 抛错时向调用方抛出，不吞掉数据库错误。

## Testing

本 change 按 TDD 执行，重点测试：

- public API 可导入。
- 空结果返回全 0 summary。
- 多条 agent_run_completed 聚合 run_count / tokens / elapsed。
- 按 user / agent / tenant / session / 时间范围过滤。
- by_model 聚合和排序。
- 缺失或非法 payload 字段不导致异常。
- 只统计 agent_run_completed，不统计其他 event_type。
- 实现不直接查询 traces 表，而是通过 `query_trace_events()`。

## Future Work

后续独立 changes：

- `platform-observability-dashboard`
- `usage-rollups`
- `quota-from-usage-summary`
- `model-cost-catalog`
- `tool-and-llm-step-metrics`
