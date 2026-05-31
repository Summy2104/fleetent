## Why

observability 是后续 memory、long-term-ctx、reflection 和 knowledge-base 自动化效果验证的证据来源。
它比语义类模块更适合先做自动化验证，因为主要验证结构性契约：事件是否写入、run_id 是否能串联、
payload 是否脱敏/截断、query 与 usage 聚合是否稳定。

当前已有单元测试覆盖 trace API、usage summary 和部分 agent_loop 接入，但缺少一组端到端 contract tests
把“agent run -> injected_context -> agent_run_completed -> query -> usage”串起来。这个 change 只补测试，
不改变运行时行为。

## What Changes

- 新增 `tests/integration/` 下的 observability contract tests，覆盖一次 agent run 的关键 trace contract。
- 验证 non-streaming run：
  - 有 long-term context sources 时写入 `injected_context`
  - 完成时写入 `agent_run_completed`
  - 两类事件共享同一个 `run_id`
  - `query_trace_events()` 可按 run_id 和 event_type 查询
- 验证 streaming run 也满足相同 source attribution / completion contract。
- 验证 source attribution payload 不保存完整 memory / KB content。
- 验证 sensitive payload 经过 redaction，large payload 经过 truncation。
- 验证 usage summary 只统计 `agent_run_completed`，忽略 `injected_context` 等其他事件。

## Capabilities

### Modified Capabilities

- `observability`：补充 contract-level 自动化验证，不改变 public API。

## Impact

- **代码**：不修改运行时代码，除非测试暴露现有 contract bug。
- **测试**：新增或重组 observability contract tests。
- **数据**：无 schema 变更。
- **不包含**：
  - 不新增 trace event type。
  - 不实现 UI。
  - 不做 memory / reflection / KB 语义效果评估。
  - 不做 OpenTelemetry / 外部 APM 集成。
