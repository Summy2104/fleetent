# trace-tool-spans

## Why

traces 表当前只记 3 种事件（`agent_run_completed` / `injected_context` / `skill_hit`），**没有任何 tool 级 span**，且 run 级事件的 `session_id` 全为空（schema 列已存在、写入点未绑定）。2026-06-12 事故复盘时，"send_file 到底有没有被调用"这种最基本的问题无法从可观测层回答，只能靠 stdout 日志 + 审批表 + Slack 历史三方拼图考古——可观测层对"这次对话实际执行了什么"是黑盒。后续 delivery-receipts 等治理机制也依赖 tool 级事件作为事实底座。

## What Changes

- **新增 tool_call trace 事件**：agent loop 在工具**真实执行**完成后（run 与 run_stream 两路、含恢复 run 与 sub_agent run），为每次工具调用写一条 `tool_call` trace 事件：工具名、脱敏后入参摘要、成败、耗时、风险级、tool_call_id；审批 placeholder / guardrail 短路等未真实执行的 slot 不产生事件。
- **入参脱敏**：payload 中的 tool_args 经既有 `tool-arg-secret-redaction` 基线脱敏后落库，并截断到固定上限防膨胀。
- **修复 run→session 绑定**：`agent_run_completed`、`injected_context`、`skill_hit` 及新增 `tool_call` 事件统一携带 `session_id`（schema 列已存在，仅补写入点），使"按会话重建执行轨迹"成为一条 SQL。
- **零 schema 迁移**：traces 表的 `span_id`/`session_id`/`payload_json` 列足够承载，本变更不动表结构。

## Capabilities

### New Capabilities

- `trace-tool-spans`: 工具调用级 trace 事件（真实执行才记、脱敏入参、成败/耗时/风险）与 run 级事件的 session 归属绑定。

### Modified Capabilities

（无——`observability` 现 spec 仅覆盖 structured logging，其 Purpose 明示 run traces 由后续 change 独立扩展；本 change 即该扩展，作为新 capability 承载，不改既有 requirement。）

## Impact

- **代码**：`observability/traces.py`（事件记录 API 增加 tool_call 与 session_id 参数）；`runtime/loop.py`（backfill 阶段真实执行点挂接、`log_run` 调用补 session_id）；`observability/__init__.py` public API。
- **owned tables**：无新表（复用 traces）。
- **config namespace**：无。
- **依赖方向**：runtime → observability（既有方向），零 platform import。
- **关联**：`delivery-receipts-postcondition` 的回执事件复用本底座（依赖序在后）。
