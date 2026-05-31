## Why

fleetent 当前的 agent run trace 仍由 `eval_logger` 以 append-only JSONL 写入
`data/traces.jsonl`。这个模式在 MVP 早期足够简单，但已经不适合后续 reflection、platform
trace view、usage metrics 和 source attribution：

- JSONL 不适合按 user / agent / run / event_type / 时间窗口高频查询。
- `log_run()` / `log()` 命名含义混乱，容易和 structured logging 的 `log` 语义冲突。
- `fleetent.eval_logger` shim 会让新旧边界长期并存，增加维护成本。
- 现在还没有正式使用，不需要承担旧 JSONL 兼容和导入成本。

本 change 将 agent run traces 一步迁到 observability-owned SQLite event store，并删除旧 API。

## What Changes

- 新增 observability-owned SQLite `traces` 表。
- 新增明确的 trace public API：
  - `record_trace_event(event)`
  - `query_trace_events(query)`
  - `TraceEvent`
  - `TraceQuery`
- 删除 `log_run()` / `log()` public API。
- 删除 `fleetent.eval_logger` compatibility shim。
- 删除 `TRACE_PATH` / `data/traces.jsonl` 写入语义。
- 更新 agent-runtime 调用新 trace API。
- 不导入旧 JSONL，不保留兼容 wrapper。
- `log` 命名只保留给 structured logging，例如 `get_logger(component).info(...)`。

## Capabilities

### New Capabilities

- 无新增 capability；扩展既有 `observability` capability 的 Agent Traces 子域。

### Modified Capabilities

- `observability`：新增 SQLite trace event store、trace record/query API、旧 eval_logger API 删除规则。
- `agent-runtime`：运行结束时通过 `record_trace_event()` 写 agent run trace。

## Impact

- **代码**：
  - 新增 trace event 数据模型和 query 模型。
  - 新增 `record_trace_event()` / `query_trace_events()`。
  - 移除 `src/fleetent/eval_logger.py` shim。
  - 移除或替换 `fleetent.observability.eval_logger` 中旧 JSONL 实现。
  - 更新 `agent_loop` 对 `log_run()` 的调用。
- **数据库**：
  - 新增 Alembic migration 创建 `traces` 表和索引。
  - 通过 database runtime 访问 SQLite。
- **测试**：
  - 删除或重写 legacy eval_logger JSONL 测试。
  - 新增 trace record/query、agent_loop 集成、无 JSONL 写入、旧 API 删除的测试。
- **不包含**：
  - 不实现 structured logging；该能力由 `2026-05-31-observability-structured-logging` 负责。
  - 不实现 source attribution 接入。
  - 不实现 metrics 聚合。
  - 不实现 platform trace UI。
  - 不引入 OpenTelemetry。
