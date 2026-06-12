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

**现状勘查结论**（实现前，经 Explore 代理确认）：
- `outbound.py` 已有 `send_to(... target_type, thread, blocks)` / `send_file_to(... target_type, thread)`，平台分派齐全，**无 origin dict 解析**。
- cron 的 origin 解析在 `cron_scheduler.py::_resolve_delivery`（line 217-235），把 `{platform, chat_id, target_type, thread_id}` 解析为 `(platform, target, target_type, thread)` tuple——top-level 模块，可 import outbound，无 platform 边界问题。
- `NormalizedMessage`/`SessionContext` 在 `im_gateway/normalizer.py`（SessionContext 字段：platform, sender_id, sender_name, chat_type, channel_name, was_mentioned, thread_root）。
- 挂起条目在 `loop.py` ~840-848：`{approval_id, tool_call_id, tool_name, tool_args, risk, approver_ids}`——**无 address**。run() 作用域有 session_id、user_id；但 NormalizedMessage/SessionContext **不在 loop 作用域**（loop 只收 session_id/principal/reply_func）。
- 恢复三入口：`normalizer.route()` 文本 approve（line 361-416）→ `_resume_pending_in_session`（line 288，`continue_run` **不传 upload_func**）；`slack.handle_approval_action`（line 159，重建 `_reply` 无 thread、`resume_msg` 无 upload_func、SessionContext 仅 2 字段）。
- session 持久化：`session/manager.py` `add/get/remove_pending_approval`，entry 是 JSON dict 存 `meta.pending_approvals[approval_id]`。

**关键决策：**
- **D②-1 address 来源**：loop 作用域无 NormalizedMessage。故 `ConversationAddress` 由**入站 adapter 构造**并经 `session_context`/新增管道带到 loop 挂起点。最小改动方案：把 address 作为 `session_context` 的衍生（SessionContext 已含 platform/thread_root 等），在挂起时由 loop 从传入的 `session_context` + session_id 构造 address dict 存入 pending 条目。→ 需给 `run()` 暴露 address 或从 session_context 提取。**采用**：`ConversationAddress` 提供 `from_session_context(session_context, channel_id, user_id)` 工厂；loop 挂起点已有 session_context 访问（经 ToolContext/参数）——确认 loop 是否有 session_context 形参，无则新增可选参数。
- **D②-2 ConversationAddress 落 outbound.py**（顶层基础设施，im_gateway 与 runtime 都已依赖，零新方向；放 normalizer 会致 runtime→im_gateway 反向 import）。frozen dataclass `{platform, chat_id, target_type, thread_id, user_id}` + `chat_type`/`thread_root`（恢复 SessionContext 用）。
- **D②-3 cron origin 收敛**：`ConversationAddress.from_cron_origin(dict)`，`_resolve_delivery` origin 分支经它构造再取投递 tuple，行为不变。
- **D②-4 工厂**：`make_replier(connectors, address)→reply_func(text, blocks=None)`、`make_uploader(connectors, address)→upload_func(paths)`，内部走 send_to/send_file_to，零平台分支。
- **D②-5 降级**：旧 pending 无 address → 恢复回退触发消息上下文 + warning，不阻塞。

**实现要点与决策（apply 阶段）：**
- **D②-6 单收敛点修复三入口**：按钮/文本/重启三个恢复入口**全部经 `_resume_pending_in_session`**。故只在该函数内从持久化 address 重建 reply_func（`make_replier`）/upload_func（`make_uploader`）/SessionContext/conversation_address，三入口一并修复——**无需改 `slack.handle_approval_action` 与文本 approve 路径本身**（它们构造的"触发消息上下文"被 resume 函数忽略，仅作为 outbound_connectors/user_id/agent_name 的载体；缺 address 时才回退到它）。故 tasks 3.5-3.8 由这一个收敛点满足；契约测试 `test_resume_address_contract.py` 用「故意错误的触发上下文（顶层 DM 无 thread）+ 持久化 thread 地址」证明三入口等价。
- **D②-7 upload 在 resume 的实际通道**：`upload_func`（NormalizedMessage 字段）实际**无人消费**——真正的文件外发是 `send_file` 工具读 `tool_context.session_context`（platform/sender_id/chat_type）+ `outbound_connectors`。故 resume 的关键是重建 `session_context`（已做），`make_uploader` 仍构造以证明能力已接线（绑定但 send_file 才是投递路径）。
- **D②-8 progress 保证**：resume 时 `progress_func = msg.progress_func or _noop_progress`，保证"progress 可用"契约即便触发入口未带 progress。
- **D②-9 telegram**：无 Slack 式 thread（reply_to 是回复链非论坛 topic），故 telegram address `thread_id=None`；telegram 当前未接审批按钮入口，仅入站构造 address 以保持结构一致。
- **5.2 真机验证**：同 ①，无 live IM/model 环境，自动化契约测试（错误触发上下文→回原 thread）等价覆盖；live my-bot 事故场景重放待用户环境。

---

## ③ unified-file-exchange

待执行。

---

## ④ delivery-receipts-postcondition

待执行。
