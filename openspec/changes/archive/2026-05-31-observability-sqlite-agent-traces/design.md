## Overview

本 change 将 agent run traces 定义为 observability 管理的 SQLite event store。它只负责记录和查询
agent 运行事件，不负责程序日志。程序日志使用 structured logging 的 logger API；agent trace 使用
`record_trace_event()` / `query_trace_events()`。

## Naming Boundary

最终命名边界：

- Structured logging：
  - `get_logger(component)`
  - `logger.info(...)`
  - `logger.error(...)`
- Agent run traces：
  - `record_trace_event(event)`
  - `query_trace_events(query)`
  - `TraceEvent`
  - `TraceQuery`

本 change 禁止继续暴露顶层 `log()` 或 `log_run()` trace API。`log` 语义留给 structured logging。

## Public API

`fleetent.observability` 导出：

```python
@dataclass(frozen=True)
class TraceEvent:
    run_id: str
    event_type: str
    payload: dict[str, Any]
    id: str | None = None
    ts: datetime | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    tenant_id: str = "default"


@dataclass(frozen=True)
class TraceQuery:
    run_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    tenant_id: str | None = None
    event_type: str | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    limit: int = 100


def record_trace_event(event: TraceEvent) -> None:
    """Record one agent run trace event."""


def query_trace_events(query: TraceQuery) -> Iterator[TraceEvent]:
    """Query agent run trace events."""
```

`id` 和 `ts` 可由调用方传入；未传入时由 observability 生成。`run_id` 由 agent-runtime 在 run 入口生成。

## Database Schema

新增 Alembic migration：

```sql
CREATE TABLE traces (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  span_id TEXT,
  parent_span_id TEXT,
  session_id TEXT,
  user_id TEXT,
  agent_id TEXT,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  event_type TEXT NOT NULL,
  ts DATETIME NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX idx_traces_run_id ON traces(run_id);
CREATE INDEX idx_traces_user_ts ON traces(user_id, ts);
CREATE INDEX idx_traces_agent_ts ON traces(agent_id, ts);
CREATE INDEX idx_traces_tenant_event_ts ON traces(tenant_id, event_type, ts);
```

## Initial Event Coverage

本 change 先迁移现有 `log_run()` 能表达的信息，不要求一次接满所有细粒度事件。

第一版至少记录：

- `agent_run_completed`
  - user input 摘要或完整值（按截断规则）
  - final reply 摘要或完整值（按截断规则）
  - serialized messages（按截断规则）
  - elapsed seconds
  - token usage
  - model used
  - user id
  - agent id / agent name

后续 changes 再逐步增加：

- `llm_call_started` / `llm_call_completed`
- `tool_call_started` / `tool_call_completed`
- `approval_requested` / `approval_resolved`
- `context_compacted`
- `injected_context`

## Redaction And Truncation

payload 写入前必须复用 observability redaction baseline。大字段需要截断：

- 字符串超过阈值时保留前后片段，并写入 `truncated=true` 元信息。
- messages 数组过大时保留关键开头和结尾，避免 trace 表膨胀。
- 工具参数和返回值必须先脱敏再截断。

第一版阈值可通过常量定义；配置化可后续补充。

## Legacy Removal

本 change 不做向后兼容：

- 删除 `log_run()`。
- 删除 `log()`。
- 删除 `TRACE_PATH`。
- 删除 `fleetent.eval_logger` shim。
- 删除 `data/traces.jsonl` 写入逻辑。
- 不导入旧 JSONL 文件。

测试中应断言旧 import 或旧 API 不再可用，避免兼容层残留。

## Query Semantics

`query_trace_events()` 支持按以下维度过滤：

- `run_id`
- `user_id`
- `agent_id`
- `tenant_id`
- `event_type`
- `start_ts`
- `end_ts`
- `limit`

默认按 `ts ASC` 返回，便于展示一次 run 的时间序事件流。跨 run 查询如需倒序可在后续 API 增加
`order` 参数；本 change 暂不加入。

## Error Handling

- trace 写入失败不应静默吞掉；agent-runtime 应记录 structured error log，并继续按现有错误策略处理。
- payload JSON 序列化失败时，应转字符串并标记 `serialization_fallback=true`。
- unsupported database backend 行为沿用 database-runtime 的 fail-fast 规则。

## Testing

本 change 按 TDD 执行。重点测试：

- Alembic migration 创建 traces 表和索引。
- `record_trace_event()` 写入 SQLite。
- `query_trace_events()` 按各维度过滤。
- payload 序列化、脱敏、截断。
- agent_loop 完成后写 `agent_run_completed` trace。
- run_stream 完成后写 trace 并包含 token usage。
- 不创建或追加 `data/traces.jsonl`。
- `fleetent.eval_logger`、`log_run()`、`log()`、`TRACE_PATH` 不再作为 public API 存在。

## Open Questions

- `run_id` 使用 UUID 还是 ULID：本 change 建议使用 ULID，因 platform 已需要按时间排序的 request/run id。
- `agent_id` 与 `agent_name` 的最终字段关系：当前代码多处使用 agent_name；本 change 可先在 payload 保留
  agent_name，并在顶层 `agent_id` 可用时写入。
