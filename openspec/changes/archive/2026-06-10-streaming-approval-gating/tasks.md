## 1. run_stream opt-in 审批门控

- [ ] 1.1 Write failing tests:`tests/unit/test_agent_loop_stream_approval.py` —— `stream_approvals=True` 时,mock `_default_gate.request_approval` + mock LLM 产一个需审批工具调用;断言事件序列中 `approval_required`(含 approval_id/tool/risk)出现在审批等待之前;`stream_approvals=False`(默认)时不调用 gate、不产 `approval_required`(回归保护)
- [ ] 1.2 Implement:`run_stream` 加 `stream_approvals: bool = False`;开启时流式 dispatch 走门控分支——审批阻塞前先 emit `approval_required` 事件再 `await request_approval`(复用 run() 的串行/原序审批次序)使测试转绿

## 2. 放行 / 拒绝语义

- [ ] 2.1 Write failing tests:批准→被审批工具的 `tool_call`/`tool_result` 正常产出;拒绝→该 run 按 `approval_rejected` 终止(写占位 tool_result、下个 while-top 终止),不泄漏未配对 tool 事件
- [ ] 2.2 Implement:批准入批执行;拒绝置 `LoopState.approval_rejected`(复用 AR1 `ApprovalRejectedChecker`,不新增 StopReason)使测试转绿

## 3. tui-gateway 启用

- [ ] 3.1 Write failing tests:`tests/unit/test_tui_dispatch.py`(扩展)—— `send` 以 `stream_approvals=True` 调 run_stream;当 run_stream 产 `approval_required` 时,网关透传为 `event` 通知(FakeTransport + mock run_stream 注入该事件)
- [ ] 3.2 Implement:`tui/dispatch.py` 的 `_stream_run`/`send` 传 `stream_approvals=True`(事件透传与 render 已具备,无需改 render)使测试转绿

## 4. 收尾

- [ ] 4.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 通过;`uv run ruff format && uv run ruff check` 仅校验本 change 文件;`uv run mypy src` 不新增错误模式
- [ ] 4.2 更新 spec 范围说明的回指(tui-gateway 里“待 streaming-approval-gating 落地”→标注已落地);PR 说明对 SSE `/chat` 的零影响(opt-in 默认关)
