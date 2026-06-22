# Tasks

> 每个实现 task 严格 TDD：先写测试跑最窄命令**见红** → 写实现**见绿**。
> 测试任务排在对应实现任务之前。基线对照 main（门禁判据＝无新增失败）。
> 最窄命令：`uv run pytest tests/unit/test_loop_terminal_status.py -x -q`

## 1. 前置核实

- [ ] 1.1 复读 `loop.py` 两处 finalize（`run` ~2086 / `run_stream` ~2806）的 `reply` 计算 + budget grace 块；确认 tool 结果为 `{"role":"tool","content":<str>}`（~983/2786）；确认 `StopReason` 已在 loop.py 导入

## 2. 纯函数：_last_tool_error / _terminal_status_reply / _finalize_reply（TDD：红 → 绿）

- [ ] 2.1 **测试先行**：新建 `tests/unit/test_loop_terminal_status.py`：
  - `_last_tool_error`：多条 tool 取最后；空白归一化 + 截断；无 tool→None；非 dict/无 content 跳过
  - `_terminal_status_reply`：loop_detected+tool err→含 prefix+err+「请换个方式」；consecutive_failures 同；loop_detected 无 tool→仅 prefix；approval_rejected / cancelled→各自文案；normal / budget_exceeded / awaiting_approval / mcp_strict_unavailable→None
  - `_finalize_reply`：非空原样；空+loop_detected→状态文案；空+normal→原空；"  " 视为空
  跑最窄命令 **见红**（函数不存在）
- [ ] 2.2 **实现**：`loop.py` 新增模块级 `_last_tool_error` / `_terminal_status_reply` / `_finalize_reply`（纯函数、完整类型注解 + docstring）。跑 2.1 **见绿**

## 3. 接线两处 finalize（wiring）

- [ ] 3.1 `run`（budget grace 块之后、`_apply_output_transform` 之前）：`reply = _finalize_reply(reply, stop_reason, messages)`
- [ ] 3.2 `run_stream`（同位置）：`_final = _finalize_reply(reply, stop_reason, messages); if _final != reply: reply = _final; yield {"type":"text_delta","content":reply}`
- [ ] 3.3 wiring 正确性由全量回归保证（见 task 4）；逻辑正确性已由 task 2 纯函数测试覆盖

## 4. 回归 + lint

- [ ] 4.1 全量 loop/run 回归不破坏既有行为：`uv run pytest tests/unit/test_loop_detector.py tests/unit/test_loop_approval_suspend.py tests/unit/test_agent_loop.py tests/unit/test_hook_on_run_complete.py tests/unit/test_slack_assistant.py -q` 全绿（含空回复守卫、正常完成、审批挂起不回归）
- [ ] 4.2 `uv run ruff check` + `ruff format --check` `src/fleetent/runtime/loop.py` + 测试 通过

## 5. spec 同步

- [ ] 5.1 确认 `specs/agent-loop-termination/spec.md` 新增「异常终止不返回空回复」要求与实现一致，含 loop_detected（带最后错误）/ cancelled / normal-不触发 等 scenario

## 6. 收尾验证

- [ ] 6.1 `make test-pr`：全绿或仅预先存在且无关失败（判据＝无新增失败）
- [ ] 6.2 模块边界自检通过；无 `fleetent.platform.*` 反向 import
- [ ] 6.3 回归确认（人读）：正常完成 / budget grace / 审批挂起 / 空回复守卫均未变；仅新增「异常终止 + 空回复 → 合成状态文案」
