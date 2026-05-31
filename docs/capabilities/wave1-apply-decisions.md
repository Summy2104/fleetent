# Wave-1 Apply 决策日志

> 全自主 apply 期间，遇到的冲突 / Open Question 及其解决记录，供 zy 最后核实。
> 每个 change 一节：遇到什么、怎么解的、影响。

## error-classification (AR5) — feat/error-classification

**前置核实结论(openai SDK 2.36.0):**
- `context_overflow` 判据：`APIStatusError` 且 `error.code == "context_length_exceeded"`（上下文超限以 400 + 该 code 呈现，仅状态码无法与普通 400 区分，故以 code 为准）。
- `auth_failed` 判据：`APIStatusError` 且 `status_code in {401,403}`（`AuthenticationError`/`PermissionDeniedError` 本就是 401/403，状态码判据自然覆盖，无需对子类单独 isinstance）。

**自行解决的冲突：**
1. tasks 提到的 `agent-runtime.md` 不存在 → 预留码标志位以 design.md D3 明确取值为准（tool_timeout/sandbox_* 全 False，mcp_disconnect 仅 should_retry）。
2. `tool_crash` 在表中但 `classify()` 永不返回（工具崩溃在 _safe_dispatch 归一化为字符串、不抛给 classify）→ 保留为词汇表项，守卫测试只断言不产出 4 个预留码。
3. `run_stream` 异常出口原 `return` 跳过了 log_run → 补 `_log_run_error` 在 return 前写 error_category，使"fallback 耗尽记分类码"对流式路径也成立。
4. ruff format 会误改 47 个无关文件 → 已还原，仅留本 change 的 6 个文件。

**影响：** 新增 error_classifier.py；agent_loop fallback 判定改读 should_switch_model（行为等价）；log_run 加 error_category 字段。416 passed，ruff/mypy 无新增（agent_loop 的 N814 _CU 为 AR1 既有遗留）。
**需 zy 核实：** 上述判据 #2（tool_crash 不产出）与 #3（流式补写 trace）是否认可。
