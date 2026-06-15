## Why

`send_file` 当前永远把文件投到请求者的私信（用 `session_context.sender_id` + `outbound.send_file_to` 默认 `target_type="user"`）。在频道里 @bot 要文件时，文本回复正确落在频道、文件却跑到私信——与「文件回当前对话」的直觉和工具 docstring（"DM or the current channel"）不符。根因是文本回复用权威的 `conversation_address`（`platform/chat_id/target_type/thread_id`，`make_replier` 在用），而 `send_file` 没用它；`SessionContext` 本身不带 `channel_id`，光靠它修不了。

## What Changes

- `ToolContext` 新增 `conversation_address` 字段（可选），由 IM 网关 run 路径注入——与文本回复同源的权威投递地址。
- `send_file` 收件人解析从「`sender_id` 恒 DM」改为「当前对话地址」：有 `conversation_address` 时按其 `chat_id`/`target_type`/`thread_id` 投递（频道→发频道并挂 thread、私信→发私信），缺失时回退旧 `sender_id` DM 行为（standalone / 流式 / 无网关路径向后兼容）。
- 收件人仍由 harness 固定、仍不接受任何模型提供的收件人参数、LLM schema 仍只暴露 `path`——核心安全契约不变，仅「发去哪」从「恒私信」变为「当前对话」。
- **BREAKING（行为）**：频道会话中 `send_file` 由「发到请求者私信」变为「发到当前频道」。无审批语义变化（`send_file` 仍恒免审批，见下）。
- 规格对账：移除 `sandbox-file-send` 中已被 `approval-boundary-redesign`（#259，`send_file` 恒免审批）取代的过时要求「send_file 免审批当且仅当盒子封闭且收件人受约束」——该要求要求「频道会话升级审批」，既与现行代码（`approval_policy.risk_for` 对 `send_file` 恒返回 `none`）不符，也与本次「频道→发频道」行为直接冲突。审批权威归 `approval-policy` 单一来源。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `sandbox-file-send`: `send_file` 收件人从「`sender_id` 恒私信」改为「当前对话地址」（频道→频道、私信→私信，harness 固定、无模型参数契约不变）；并移除已被 `approval-policy` 取代的过时「频道升级审批」要求。

## Impact

- `src/fleetent/tools/registry.py`：`ToolContext` 加 `conversation_address` 字段。
- `src/fleetent/runtime/loop.py`：IM 网关 run 路径的 `ToolContext` 构建点注入 `conversation_address`。
- `src/fleetent/tools/builtin_tools.py`：`send_file` 用 `conversation_address` 解析收件人（透传 `target_type`/`thread` 给 `outbound.send_file_to`），缺失时回退。
- `outbound.send_file_to` 已支持 `target_type`/`thread`，签名不变。
- `send_file` 工具 LLM schema 不变（仍只 `path`）；`approval_policy` 不变（`send_file` 恒 `none`）。
- 测试：`tests/unit/test_tool_registry.py`（字段）、`send_file` 行为单测（频道→频道、私信→私信、回退）。
- 无数据迁移、无 config 变更、无 owned table 变更。
