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

## message-hygiene (AR6) — feat/message-hygiene

**实现：** 新增 message_hygiene.py（`sanitize(messages)->(clean,report)` 纯函数、`RepairKind`/`HygieneReport`/`MessageContractError`、三类修复按 D2 顺序、幂等）；run/run_stream 在 maybe_compress 后 LLM 前接入；log_run 加 hygiene_repairs 字段；不可修复 raise 由主循环按错误处理。

**MessageContractError 对齐 AR5：** 它是普通 Exception，经 AR5 `classify()` 落到 `unknown`（正是 design Open Question 预期），复用 `_log_run_error` 在循环出口写 `error_category="unknown"`。

**⚠️ 编排者验证抓到的关键 bug + 修复（重点核实）：** AR6 agent 最初把 run() 改为操作 sanitize 的副本（rebind `messages = sanitize(...)`），但 `im_gateway/normalizer.py:105-112` 的 IM 路径**依赖 run(history) 就地改 history** 再 `save(session_id, history)` 持久化（其注释明写"run already appended in-place, do NOT append again"）。rebind 会让 history 收不到 assistant/tool 追加 → **每个 IM session 只存到 [system,user]、丢失 AI 回复**（449 测试未覆盖故未报）。
**解法：** run() 改用**就地内容赋值** `messages[:] = maybe_compress(messages)` 与 `messages[:] = clean`，保住调用方列表引用（顺带也修了 maybe_compress 压缩时同样的 detach 隐患）。新增回归测试 `test_run_mutates_caller_messages_in_place` 守卫此契约。run_stream 的 messages 为内部局部变量、无外部 save 依赖，不受影响。

**agent 自解冲突：** 同名占位可达性（重写为实际可达用例）、test mock 的 model_dump 返回真 dict、stale 行号更新。

**影响：** 450 passed。run() 现保证就地改调用方 messages（IM 持久化正常）。
**需 zy 核实：** 上述就地赋值修复（run() mutation 契约）是否认可；MessageContractError→unknown 的处理是否认可。
