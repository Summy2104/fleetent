## Why

两个 `send_im_message`（私发他人/发频道，medium 审批）的 UX 缺陷：

1. **审批弹窗不显示「发给谁」**：`approval_prompt_blocks(approval_id, tool_name, risk_level)` 不接收工具参数，弹窗只显示工具名+风险+ID。用户看不到收件人，无法确认是不是要发的人就批准了——审批失去把关意义。
2. **发送成功后当前会话无反馈**：审批通过后 resume 执行 send_im_message、把结果作为 context 喂回模型续跑，但发送回执记在 resume 的 tool_context ledger（未设）、续跑是另一个 run 的 ledger，系统的「📬 实际投递」fact trailer 渲染不出来；最终是否反馈全看模型自由发挥，用户感知不到通知成功与否。

## What Changes

- **审批弹窗显示收件人摘要**：审批 prompt（按钮版 blocks + 文本版）SHALL 携带本次受门控调用的人类可读摘要。对 `send_im_message`：收件人（解析为显示名「@张三」/「#频道名」，best-effort 经连接器 `users.info`/`conversations.info`，失败回退 raw id）+ 类型（私信/频道）+ 文本预览 + 附件数；其他受门控工具给通用参数摘要。名称解析 best-effort + 短超时，失败/超时不阻断弹窗（回退 raw id）。
- **审批通过后确定性投递回执**：恢复执行受门控工具时，其投递回执 SHALL 进入续跑最终回复的「📬 实际投递」fact trailer——通过在 resume 的 tool_context 与续跑 run 之间共享 delivery ledger 实现，使「已通知 X」成为系统确定性输出，不依赖模型。
- `outbound.approval_prompt_blocks` 增加 `summary` 文本参数；新增 best-effort 收件人名解析 + 调用摘要 helper（async，零 platform 依赖）。
- `runtime/loop.run` 接受可选 `delivery_ledger` 注入（默认仍内部新建），供 resume 续跑复用同一 ledger。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `permission-gate`: 审批 prompt（交互按钮 + 文本）除工具名/风险/ID 外，SHALL 携带受门控调用的人类可读摘要（send_im_message 显示名解析的收件人 + 类型 + 文本预览 + 附件数）。
- `approval-suspend-resume`: 恢复执行受门控工具产生的投递回执 SHALL 出现在续跑最终回复的事实投递尾注中（确定性反馈），经共享 delivery ledger 实现。

## Impact

- `src/fleetent/outbound.py`：`approval_prompt_blocks(..., summary=...)`；新增 `resolve_recipient_label()` + `summarize_gated_call()`（async，best-effort，raw-id 回退）。
- `src/fleetent/governance/permission_gate.py`：requester prompt + 外部 approver 通知两处构建摘要（await 名解析、超时回退）并传入 prompt blocks/文本。
- `src/fleetent/runtime/loop.py`：`run()` 增加可选 `delivery_ledger` 注入。
- `src/fleetent/im_gateway/normalizer.py`：`_resume_pending_in_session` 建共享 ledger，挂到 resume tool_context（+ run_id）并传入 `continue_run` 的 `run()`。
- 测试：`approval_prompt_blocks`/摘要 helper 单测、permission_gate 携带摘要单测、resume 投递回执进 trailer 单测。
- 无数据迁移、无 config 变更、无 owned table 变更；审批触发条件与风险分级不变（仅丰富 prompt 展示与成功反馈）。
