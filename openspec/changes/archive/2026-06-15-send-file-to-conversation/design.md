## Context

`send_file(path)` 是宿主侧内置工具，把 workspace / `/exchange` 工件作为附件送回当前对话。文本回复经 `make_replier(connectors, address)` 用权威 `ConversationAddress`（`platform/chat_id/target_type/thread_id`，由 IM 适配器构建一次、贯穿 suspend/resume）投递，能正确回到频道或私信。但 `send_file` 的收件人解析（`tools/builtin_tools.py`）走的是 `tool_context.session_context.sender_id` + `outbound.send_file_to(...)` 默认 `target_type="user"`，因此**无论频道还是私信，文件恒投到请求者的 DM**。

`SessionContext`（`im_gateway/normalizer.py`）只有 `chat_type`/`channel_name`，**不带 `channel_id`**，所以仅凭它无法把文件发回频道。而 `conversation_address` 已作为参数贯穿 `loop.run`（多层签名），在 `ToolContext` 构建点的作用域内，只是没接到 `ToolContext` 上。

`outbound.send_file_to(platform, connector, target, path, *, target_type="user", thread=None)` 已原生支持频道投递（`target_type="channel"`）与 thread，无需改签名。

审批语义已由 `approval-boundary-redesign`（#259）settled：`approval_policy.risk_for` 对 `send_file` 恒返回 `none`（无收件人参数=恒回当前对话=非外发）。`sandbox-file-send` spec 仍残留更早的「免审批当且仅当…DM、频道升级审批」要求，与现行代码及本次「频道→发频道」均冲突，属待对账的过时要求。

## Goals / Non-Goals

**Goals:**
- `send_file` 文件落到与文本回复**完全相同**的当前对话位置：频道→发频道（挂 inbound thread）、私信→发私信。
- 复用权威 `conversation_address`，单一投递地址来源，避免 `send_file` 自行拼地址而与文本回复漂移。
- 保持核心安全契约：收件人 harness 固定、不接受模型收件人参数、LLM schema 仍只 `path`。
- 向后兼容：无 `conversation_address` 的路径（standalone CLI、流式、无网关）回退旧 `sender_id` DM 行为。
- 规格对账：移除 `sandbox-file-send` 已被 `approval-policy` 取代的过时审批要求。

**Non-Goals:**
- 不改 `send_file` 审批语义（仍恒免审批，权威在 `approval-policy`）。
- 不改 `send_im_message`（其收件人本就由模型指定、恒按接收方身份轴判审批）。
- 不改 `/exchange` 跨 scope 归属硬护栏（`resolve(approved=False)` 不变）。
- 不改 `outbound.send_file_to` 签名。
- 不改 standalone/流式路径的投递能力（它们无 `outbound_connectors`，本就返回降级文本）。

## Decisions

1. **`ToolContext` 加 `conversation_address: Any = None`**（`tools/registry.py`）。用 `Any` 避免 `tools`→`outbound` 的类型耦合在签名层固化（与既有 `session_context: Any` 一致风格），运行时是 `ConversationAddress`。`tools` 仍 MUST NOT import platform——`ConversationAddress` 定义在 `outbound`（无 platform 依赖、可序列化），合规。

2. **`loop.py` 在 IM 网关 run 路径的 `ToolContext` 构建点注入** `conversation_address=conversation_address`（该参数已在函数作用域）。流式路径（`run_stream`）无 `conversation_address` 入参、也无 `outbound_connectors`，不注入——保持其现状（无主动外发）。

3. **`send_file` 收件人解析改为「当前对话地址优先、`sender_id` 回退」**：
   - 当 `tool_context.conversation_address` 存在：`target = address.chat_id`，`target_type = address.target_type`，`thread = address.thread_id`。
   - 否则回退：`target = session_context.sender_id`，`target_type = "user"`，`thread = None`（旧行为）。
   - `session_context is None` 仍 fail-closed（无会话发起人），不变。
   - 平台仍取 `session_context.platform`（或 address.platform，两者同源）；连接器查找、`/exchange` 解析、降级与回执逻辑均不变。
   - 结果文本回显实际收件人（频道时为 `platform:chat_id`，私信时为 `platform:sender_id`）。

4. **移除 `sandbox-file-send` 过时要求「send_file 免审批当且仅当盒子封闭且收件人受约束」**（含其「频道升级审批」场景）。审批权威单一归 `approval-policy`（`send_file` 恒 `none`）。这不改任何代码行为（代码早已恒免审批），只消除 spec 内部矛盾。

5. **TDD**：先写 `send_file` 频道→频道、私信→私信、无 address 回退三个行为单测（mock `outbound.send_file_to` 断言 `target`/`target_type`/`thread`），见红；再改代码见绿。`ToolContext` 字段单测同理。

## Risks / Trade-offs

- **行为变更可见**：频道里历史上文件进私信，本次起进频道。这是修复用户报告的缺陷、且与文本回复一致，属预期改善；通过实测确认。
- **频道刷文件顾虑**：文件发频道意味着对频道成员可见。但这正是「在频道里要文件」的语义，且文本回复本就发频道；不引入新的可见面（请求者主动在频道发起）。`send_file` 仍恒免审批与 `approval-policy` 一致。
- **回退路径**：无 `conversation_address` 时静默回退旧 DM 行为，保证 standalone/流式不回归。代价是这些路径仍只能私信——但它们本就无频道上下文，无损。
- **spec 对账触及 #259 邻域**：移除的要求确属本次「频道行为」直接相关的矛盾点，非无关重构；审批权威集中到 `approval-policy` 更清晰。
