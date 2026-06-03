## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 OpenAI 兼容后端对消息序列的契约要求（角色交替、tool_call/tool_result 配对、tool 消息须带 `tool_call_id`），与现有 `agent_loop.py` 消息构造（行 221 assistant model_dump / 285 tool result / 440 stream assistant / 451 stream tool result）对齐
- [x] 1.2 核实 `run()` 审批被拒补占位（行 268-285）与 `maybe_compress` 输出，确认卫生层接入点（`maybe_compress` 之后、LLM 调用之前）不与既有保契约逻辑冲突
- [x] 1.3 确认 `log_run` 签名（eval_logger.py 行 14-25），新增末位 kw 参数 `hygiene_repairs: dict | None = None` 即向后兼容

## 2. 数据结构与入口骨架（message_hygiene.py）

- [x] 2.1 Write failing tests for `RepairKind` 枚举与 `HygieneReport` 数据类：`tests/test_message_hygiene.py` 断言枚举含 `merged_same_role` / `inserted_placeholder` / `filled_missing_tool_result` / `removed_orphan_tool_result`；`HygieneReport` 含 `repairs` / `changed`。看到红
- [x] 2.2 Implement `RepairKind`（StrEnum）、`HygieneReport`，看到绿
- [x] 2.3 Write failing tests for `sanitize()` 合法序列：传入合法序列返回内容等价的新列表、`changed=False`、且不修改入参（断言入参对象未变）。看到红
- [x] 2.4 Implement `sanitize()` 骨架（合法序列原样返回新列表 + 空报告），看到绿

## 3. 修复规则：移除孤立 tool_result

- [x] 3.1 Write failing tests：含一条 `tool_call_id` 无对应 tool_call 的孤立 tool_result → 被移除，`removed_orphan_tool_result` 计数正确。看到红
- [x] 3.2 Implement 移除孤立 tool_result 规则，看到绿

## 4. 修复规则：补缺失 tool_result

- [x] 4.1 Write failing tests：assistant 含 tool_call 但无对应 tool 消息 → 补占位「工具执行失败」result、`filled_missing_tool_result` 计数正确、补在该 assistant 消息之后。看到红
- [x] 4.2 Implement 补缺失 tool_result 规则，看到绿

## 5. 修复规则：连续同角色

- [x] 5.1 Write failing tests：相邻两条同角色文本消息 → 合并（`merged_same_role`）；tool_calls 载体相邻无法合并 → 插占位（`inserted_placeholder`）；修复后无相邻同角色违规。看到红
- [x] 5.2 Implement 连续同角色规则（按 D2 顺序在清孤立/补缺失之后执行），看到绿

## 6. 不可修复 → 尽早报错

- [x] 6.1 Write failing tests for `MessageContractError`：结构性损坏序列（如缺 role / tool 消息缺 tool_call_id 且无法归属）→ `sanitize()` 抛 `MessageContractError`，异常含违规描述。看到红
- [x] 6.2 Implement `MessageContractError` 与不可修复检测，看到绿

## 7. 幂等性守卫

- [x] 7.1 Write failing tests：对任一非法序列 `sanitize()` 一次后，再次 `sanitize()` 返回 `changed=False`（修复结果稳定、不重复修复）。看到红
- [x] 7.2 Implement 使幂等性通过（确保规则收敛），看到绿

## 8. 接入 run() 与 run_stream()

- [x] 8.1 Write failing tests：`run()` / `run_stream()` 在 `maybe_compress` 后、LLM 调用前调用 `sanitize()`；非法序列被修复后才发给 LLM；不可修复时不发起 LLM 调用。mock `get_async_client_and_config`。看到红
- [x] 8.2 Implement：两处主循环在 `maybe_compress(messages)` 之后调用 `sanitize()` 并用 clean 列表替换 `messages`；捕获 `MessageContractError` 时按错误处理（不调 LLM）。看到绿

## 9. trace 写入修复动作

- [x] 9.1 Write failing tests：发生修复时 `log_run` 收到 `hygiene_repairs`；未修复时不写该字段。看到红（先验证 log_run 尚未接收 hygiene_repairs）
- [x] 9.2 Implement：`log_run` 增加 `hygiene_repairs: dict | None = None`（默认 None 向后兼容，非 None 写入 entry）；`run()` / `run_stream()` 在 `changed` 时传入 report。看到绿

## 10. 收尾

- [x] 10.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 10.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 10.3 `uv run mypy src` 无新增错误模式
