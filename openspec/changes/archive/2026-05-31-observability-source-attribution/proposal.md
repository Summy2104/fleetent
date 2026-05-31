## Why

`long-term-ctx` 已经实现 `BuiltContext.sources`，agent-runtime 能够在 prompt 中注入长期上下文。
但当前 observability 还没有记录“本次 prompt 实际注入了哪些 memory / knowledge 来源”。这会导致
排查回答来源、分析 memory 命中质量、后续 reflection 复盘上下文注入行为时缺少关键证据。

本 change 将来源归因作为 agent trace 的一个轻量事件落入现有 `traces` 表，只保存 source summary，
不保存完整 memory 或 knowledge 内容。

## What Changes

- 新增 `InjectedContextTrace` public model。
- 新增 `record_injected_context(run_id, sources, ...)` public API。
- `record_injected_context()` 将 sources 写为 `event_type="injected_context"` 的 trace event。
- agent-runtime 在 long-term-ctx 注入后记录实际注入的 sources。
- agent-runtime 为一次 run 生成稳定 `run_id`，并在 `injected_context` 与
  `agent_run_completed` 事件中复用同一个 `run_id`。
- sources 为空时不写空 trace event。
- 默认只保存来源摘要：
  - `source_id`
  - `source_type`
  - `score`
  - `token_estimate`
  - `metadata`
- 若单个 source 的 token estimate 暂不可得，允许记录 `token_estimate=0`，但字段必须存在。
- metadata 支持 memory 与 knowledge 的追溯字段：
  - memory：`memory_type`
  - knowledge：`kb_id`、`document_id`、`chunk_id`

## Capabilities

### Modified Capabilities

- `observability`：新增 source attribution summary。
- `agent-runtime`：在注入 long-term context 后记录来源摘要。

## Dependencies

- 依赖 `observability-sqlite-agent-traces` 已完成。
- 依赖 `long-term-context-foundation` 已完成并归档。
- 不依赖 `knowledge-base-core`。

## Impact

- **代码**：
  - 扩展 `fleetent.observability` public API。
  - 修改 agent-runtime 的 long-term context 注入路径。
  - 测试中 mock `record_trace_event()` / `query_trace_events()`。
- **数据**：
  - 复用现有 `traces` 表，不新增表。
  - 新增 `event_type="injected_context"` trace event。
- **行为变化**：
  - 有长期上下文 sources 被注入时，trace 中可查到来源摘要。
  - 没有 sources 时不写空事件。
- **不包含**：
  - 不保存完整 memory / KB content。
  - 不做候选结果 debug preview。
  - 不做 sentence-level citation。
  - 不做 retrieval audit。
  - 不实现 knowledge-base search / ingest。
  - 不做 UI。
