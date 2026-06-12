# file-exchange 系列 — 自动执行决策记录

> 2026-06-12 晚启动，用户授权全自动串行执行 4 个 change，明早审核。
> 本文档记录执行过程中遇到的问题、自行做出的决策点、以及偏离 spec/计划之处，供审核。

执行顺序（串行，后者硬依赖前者）：

1. **trace-tool-spans** — 审计底座（1 spec）
2. **conversation-address-unification** — 恢复上下文（2 spec）
3. **unified-file-exchange** — 文件平面（8 spec，最大）
4. **delivery-receipts-postcondition** — 回执收口（1 spec）

每个 change 流程：main 切 worktree+分支 → opsx:apply 强制 TDD → archive+sync → push → PR → squash 合并 → 清理 worktree → 回 main。

> 本文档随各分支提交，串行携带前进（① 创建，merge 到 main 后 ② 继续 append）。

---

## ① trace-tool-spans

**现状勘查结论**（实现前）：
- `observability/traces.py` 已有 `record_trace_event(TraceEvent)`，其 `_prepare_payload` 已做「值级脱敏（`structured_logging._redact_value`，覆盖 Bearer/api_key/email/phone）+ 截断（字符串 >2KB head+tail 包裹）」。
- `skill_hit` 事件（`tools/builtin_tools.py::_record_skill_hit`）**已携带 session_id**——无需改动。缺 session_id 的只有 `agent_run_completed`（`loop._record_agent_run_completed`）与 `injected_context`（`loop._record_injected_context`→`record_injected_context`）。
- 工具执行有**两条路径**：`run()` 走三相 `_plan_run_slots`→`_execute_pending`→`_backfill_slots`；`run_stream()` 自带内联 backfill 循环（非 `_backfill_slots`）。两路都要挂 tool_call 记录。
- `_execute_pending` 返回 `dict[tc_id,(content,failed)]`，**不含耗时**。

**决策点：**
- **D①-1 耗时来源**：在 `_run_serial_group` 用 `time.monotonic()` 实测每个 slot dispatch 耗时，`_execute_pending` 返回值增加 `durations: dict[tc_id,float]`（ms）。备选「在 backfill 现量」不可行——backfill 在全部并发 dispatch 完成后串行执行，量到的是排队后时刻而非执行时长。
- **D①-2 args_summary 脱敏基线**：用 `fleetent.integrations.sandbox.is_sensitive_name`（名基黑名单，eval_logger `_redact_tool_call` 同源，SB5 single source of truth）对顶层入参 key 脱敏 → JSON 序列化 → 截断到 ≤2KB（含 `...[truncated]` 标记，确保不触发 record_trace_event 的二次包裹）。值级脱敏由既有 `record_trace_event` 管线叠加兜底。该函数（`build_tool_args_summary`）为纯函数放 traces.py，unit 可测。
- **D①-3 写入失败隔离**：`record_tool_call` **自身** try/except 吞写库异常、仅 `_logger.warn`、不抛（契合 task 1.1「写入失败仅 warning 不抛」措辞 + 设计 D4 best-effort）。
- **D①-4 run_id 传入 backfill**：`_backfill_slots` 原本无 run_id 形参，新增 `run_id` + `durations` 形参；`run()`/`run_stream()` 作用域内 run_id（1680/2261 行）与 session_id（函数形参）直接传入。
- **D①-5 零 schema 迁移**：复用 traces 表既有列，不动表结构（与 proposal 一致）。
- **D①-6 恢复路径单独挂钩（实现中发现的缺口）**：审批恢复执行 pending 工具走的是 `runtime/approval_resume.py::_execute_tool`（直接 `dispatch`），**不经** loop 的 `_backfill_slots`。spec Requirement 明确要求「含恢复 run」记 tool_call，故在 resume 路径单独挂 `record_tool_call`：`run_id` 用 `session_id or ""`（resume 在 continue_run 起新 run 之前执行，无 loop run_id，沿用 skill_hit 同款回退），session_id/agent_name 取 `tool_context`，失败（dispatch 抛错）记 `failed=true` 后**仍按原语义重新抛出**（不改恢复流程的异常行为）。

- **回归修复**：`tests/integration/test_long_term_context_runtime.py::test_injected_context_trace_receives_budget_token_estimates` 把 `record_injected_context` stub 成 2 参 lambda；本 change 给该调用加了 `session_id=` kwarg，stub 需同步成 `lambda run_id, sources, session_id=None`（并断言 session_id 透传）。顺带 ruff `--fix` 了该文件预存的 import 排序（因文件进入改动集，gate 的 changed-file ruff 会扫到）。

- **D①-7 task 4.2 真机验证的自动化替代**：环境无 live LLM API key / 运行中的 my-bot，无法跑真正的端到端对话。改用**等价的真实持久层验证**：真实落盘 SQLite（`apply_migrations` + 嵌入式 `migrate`）+ 真实 `loop.run`（仅 mock LLM 与 dispatch）+ 真实 SQL 重建。脚本 `/tmp/verify_trace_rebuild.py` 输出确认——一条 `SELECT ... WHERE session_id=? ORDER BY ts` 即重建出 `injected_context → tool_call → agent_run_completed` 时间有序序列；tool_call 含 tool/failed/duration/risk，`args_summary` 中 `api_key` 已脱敏为 `[REDACTED]`，明文 secret 不落盘。集成测试 `test_run_events_share_session_id_in_order` 是同等验证的常驻版本。**待用户在有 model provider 的环境补一次 live my-bot smoke**（不阻塞本 change 的实现完成度）。

**收尾结论**：`make test-pr` 2905 passed 全绿；`tests/integration` 分支 1954 passed / 0 fail（修复后），main 基线 1945 passed / 0 fail——**无新增失败**；`mypy src` 分支 89 == main 89，新增模块零错误——**无新增类型错误**。

---

## ② conversation-address-unification

待执行。

---

## ③ unified-file-exchange

待执行。

---

## ④ delivery-receipts-postcondition

待执行。
