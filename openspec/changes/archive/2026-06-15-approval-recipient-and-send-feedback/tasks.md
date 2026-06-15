## 1. outbound: 弹窗摘要 + 收件人名解析

- [x] 1.1 写测试（红）：`approval_prompt_blocks(approval_id, tool, risk, summary="...")` 把 summary 渲染进 section 文本；summary 空时与旧版等价
- [x] 1.2 写测试（红）：`resolve_recipient_label` —— Slack user→`@<display_name>`、channel→`#<name>`（mock 连接器 `users_info`/`conversations_info`）；连接器抛错/非 Slack→回退 raw target；绝不抛
- [x] 1.3 写测试（红）：`summarize_gated_call("send_im_message", {target,text,target_type,files}, ...)` 含「发送对象：<label>（私信/频道）」+ 文本预览（截断）+ 附件数；其他工具→通用脱敏摘要
- [x] 1.4 实现（绿）：`outbound.approval_prompt_blocks` 加 `summary` 参数；`resolve_recipient_label`（async,best-effort,短超时,raw 回退）；`summarize_gated_call`（async）

## 2. permission_gate: prompt 携带摘要

- [x] 2.1 写测试（红）：requester-routed 审批，`send_im_message` 的 prompt（blocks + 文本）含收件人摘要（mock outbound 名解析）
- [x] 2.2 写测试（红）：名解析失败时 prompt 仍发出且含 raw id（不阻断）
- [x] 2.3 实现（绿）：`permission_gate.request_approval` 在 requester prompt 分支 + `_notify_approvers` 外部 approver 分支构建 `await summarize_gated_call(...)`（平台/连接器取自 outbound_connectors + tool_args/session）并传入 `approval_prompt_blocks(summary=...)` 与文本 prompt

## 3. loop: 可注入 delivery ledger

- [x] 3.1 写测试（红）：`loop.run(..., delivery_ledger=<预置含一条回执>)` 时最终回复尾注渲染该预置回执
- [x] 3.2 实现（绿）：`runtime/loop.run` 加可选 `delivery_ledger=None`，`ledger = delivery_ledger if delivery_ledger is not None else []`，其余不变

## 4. resume: 确定性投递回执反馈

- [x] 4.1 写测试（红）：审批通过 resume 执行 send_im_message 后，续跑最终回复含「📬 实际投递」尾注（共享 ledger）；mock send_to 成功返回回执
- [x] 4.2 实现（绿）：`normalizer._resume_pending_in_session` 建 `shared_ledger=[]`，resume `tool_context` 设 `delivery_ledger=shared_ledger`+`run_id`；`continue_run` 传 `delivery_ledger=shared_ledger` 给 `agent_loop.run`

## 5. 收尾验证

- [x] 5.1 受影响层单测全绿（outbound / permission_gate / loop / resume 相关）
- [x] 5.2 `make test-pr` 全绿（无新增失败）
- [x] 5.3 `uv run pytest tests/integration -q` 对照 main 基线无新增失败
- [x] 5.4 `openspec validate approval-recipient-and-send-feedback --strict` 通过
- [x] 5.5 `uv run mypy src` 无新增错误；改动文件 ruff 净
