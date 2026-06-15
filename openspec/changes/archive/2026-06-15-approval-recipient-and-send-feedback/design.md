## Context

`send_im_message`（私发他人/发频道）经接收方身份轴判为 medium，走 permission gate。当前：
- 弹窗由 `outbound.approval_prompt_blocks(approval_id, tool_name, risk_level)` 渲染，仅含工具名/风险/ID，**不含收件人**。`tool_args`（target/text/target_type/files）在 `permission_gate.request_approval` 里是有的，只是没传进 prompt。
- 审批通过后 `im_gateway.normalizer._resume_pending_in_session` 建一个**无 delivery_ledger、无 run_id** 的 `tool_context` 交给 `approval_resume.resume_pending_approval`，后者 `_execute_tool` 跑 send_im_message → `_record_delivery` 见 ledger=None 直接跳过；随后 `continue_run` 调 `agent_loop.run(...)` 新建自己的空 ledger，`_append_delivery_trailer` 渲染空 → 无「📬 实际投递」尾注。回执记录无处可达续跑回复。

fact trailer 机制（`observability.traces.render_delivery_trailer` + `loop._append_delivery_trailer`）已存在，渲染 `📬 实际投递：消息 N（<masked target>）`，target 按审计要求脱敏。

## Goals / Non-Goals

**Goals:**
- 审批弹窗（按钮 blocks + 文本回退）显示「发给谁」：收件人解析为显示名（@用户/#频道，best-effort）+ 类型 + 文本预览 + 附件数，让用户能核对收件人再批准。
- 审批通过发送成功后，当前会话**确定性**出现系统投递回执（复用 fact trailer），不依赖模型。
- 名称解析 best-effort：失败/超时回退 raw id，绝不阻断或拖慢审批弹窗。
- 零 platform 依赖；审批触发条件/风险分级不变。

**Non-Goals:**
- 不改审批触发面（哪些操作要审批仍由 approval-policy 接收方身份轴决定）。
- 不改 fact trailer 的脱敏策略（target 仍 masked；这是审计契约）。
- 不为 send_file（恒免审批、回当前对话）加弹窗——它不走审批。
- 不引入 platform 的用户目录；名解析只经已注入的 IM 连接器 best-effort。

## Decisions

1. **`approval_prompt_blocks(approval_id, tool_name, risk_level, summary="")`**（`outbound.py`）：summary 非空时作为 section 第二行展示（「发送对象：@张三（私信）／预览：…／附件 1」）。文本 prompt 同样拼接 summary。签名向后兼容（summary 默认空）。

2. **名称解析 helper `resolve_recipient_label(platform, connector, target, target_type)`**（`outbound.py`，async，best-effort）：
   - Slack + user → `users.info`，取 `profile.display_name`/`real_name`，返回 `@<name>`；
   - Slack + channel → `conversations.info`，取 `name`，返回 `#<name>`；
   - 其他平台/失败/异常 → 返回 raw `target`。
   - 包一层短超时（如 3s），超时回退 raw id。绝不抛。

3. **调用摘要 helper `summarize_gated_call(tool_name, tool_args, platform, connector)`**（async）：
   - `send_im_message`：`f"发送对象：{label}（{私信|频道}）"` + 文本预览（截断 ~60 字）+ `附件 N`（若有）。
   - 其他工具：通用紧凑 args 摘要（复用现有 `build_tool_args_summary` 风格，脱敏长值）。

4. **gate 接线**（`permission_gate.py`）：在 requester prompt 分支与外部 approver 通知分支，调用 `await summarize_gated_call(tool_name, tool_args, platform, connector)`（平台/连接器取自 outbound_connectors + tool_args.platform / session）→ 传给 `approval_prompt_blocks(summary=...)` 与文本 prompt。await 在 gate 已是 async 上下文。permission_gate 仍 MUST NOT import platform（只用 outbound + 连接器）。

5. **共享 delivery ledger 贯通 resume**（确定性反馈）：
   - `loop.run(..., delivery_ledger=None)` 新增可选参数：`ledger = delivery_ledger if delivery_ledger is not None else []`，其余不变（trailer 仍在 finalize 渲染该 ledger）。
   - `normalizer._resume_pending_in_session`：建 `shared_ledger=[]`，resume `tool_context` 设 `delivery_ledger=shared_ledger` + `run_id`（新 run id）；`continue_run` 调 `run(..., delivery_ledger=shared_ledger)`。于是 `_execute_tool` 的 send_im_message 回执进 shared_ledger，续跑 finalize 时 trailer 渲染该回执 → 回复尾部必现「📬 实际投递：消息 1（…）」。

6. **TDD**：先写 `approval_prompt_blocks` 带 summary、`summarize_gated_call`（send_im / 通用）、`resolve_recipient_label`（mock 连接器/失败回退）、permission_gate prompt 携带摘要、resume 回执进 trailer 的红测；再实现。

## Risks / Trade-offs

- **名解析增加一次 IM API 调用（审批弹窗路径）**：best-effort + 短超时 + raw-id 回退兜底，最坏情况退化为现状（raw id），不阻断审批。
- **脱敏 vs 可读**：弹窗里收件人显示**未脱敏的显示名**（用户需要核对，这是审批的目的，信息只发给审批人本人）；而 fact trailer 仍按审计契约脱敏 target。两处目的不同，刻意区别对待。
- **共享 ledger 的边界**：仅在 resume 续跑复用；正常 inbound run 仍各自新建（默认 None）。回执只多一条（resume 执行的那次发送），不会重复计入。
- **summary 仅对 send_im_message 精细**：其他受门控工具走通用摘要，足够核对；后续可按需细化。
