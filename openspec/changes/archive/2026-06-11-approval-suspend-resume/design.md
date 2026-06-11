## Context

阻塞点已核实：`loop.py:_plan_run_slots`（~756）在 plan 阶段 `await _default_gate.request_approval(...)` 同步等待，gate 内部 `asyncio.wait_for(event.wait(), timeout)`。run 的三阶段是 plan（串行）→ execute（并行）→ backfill（串行）。`StopReason`（termination.py）已有 approval_rejected 等枚举。session manager 写 `.json.tmp→rename` 原子写，meta 是自由 dict。approve/reject 在 `normalizer.route` 最前（line 286，steering 检查之前）被 `_APPROVAL_RE` 拦截；Slack 按钮经 `slack.handle_approval_action` → `gate.resolve`。

关键协议约束：带 `tool_calls` 的 assistant 消息后必须紧跟对应 `tool_call_id` 的 tool 结果，否则下次请求 400。**placeholder 方案正是用一条合成 tool 结果立即闭合协议**，使 history 永远合法，从根上消除"半截历史"。

## Goals / Non-Goals

**Goals:**
- 审批不阻塞 run；run 遇待审批工具即结束（stop_reason=awaiting_approval），状态持久化
- resolve（按钮/文本命令，含重启后）触发恢复：批准执行+续跑、拒绝注入+续跑
- pending 期间同 session 新消息照常处理（待办式）
- 跨重启存活；过期回填一致

**Non-Goals:**
- TUI/HTTP 流式路径（维持现状阻塞，follow-up）
- 审批不阻塞后的"模态强制聚焦"（明确选待办式）
- 多 pending 并发审批的复杂编排（串行登记即可；同批多门控工具逐个登记）

## Decisions

**D1 placeholder 闭合协议，real 结果在恢复时作为 context 注入。**
待审批工具的 slot 回填 `awaiting_human_approval (id=X)` 作为其 tool_call_id 的结果——history 立即合法。批准后真实执行结果不复用已被占用的 tool_call_id，而是作为新一回合的 context 消息注入（`[审批 X 已批准，<tool> 执行结果：...]`），LLM 续跑。
- 备选：deferred-commit（pending tool_call 存 meta、canonical history 留干净、resolve 重建）。否决——pending 期间来了新消息后，旧 proposal 的时序重建很乱；placeholder 让 proposal+占位按时序落定，新消息与 real 结果都顺序追加，交错场景天然正确。

**D2 pending 状态存 session 文件 meta。**
`meta.pending_approvals: {approval_id: {tool_call_id, tool_name, tool_args, risk}}`。agent 侧落点，符合解耦红线（不写 platform 表）。`approvals` 表仍记审批生命周期（已持久化），两者按 approval_id 关联。
- 备选：只靠 approvals 表。否决——表里没有"续跑所需的 session/tool_call 绑定"，且 agent 独立运行时不应依赖管理库语义；session 文件是 agent 自包含状态的正确归属。

**D3 新 `StopReason.awaiting_approval`，不复用 approval_rejected。**
语义不同：rejected 是终态（用户拒绝、turn 结束），awaiting 是中间态（等人决定、可恢复）。run 以此结束时**不**触发 grace/budget 收尾，正常保存 session（含 pending meta）。

**D4 恢复 = 执行工具 → 注入结果 context → 复跑 run。**
恢复入口 `resume_pending_approval(session_id, approval_id, decision)`：加载 session → 取 pending 条目 → 批准则经 registry.dispatch 执行该工具（复用 tool_context 注入，含 outbound_connectors），拒绝则生成拒绝文本 → 把结果作为一条 context 消息追加 history → 调 loop.run 续跑到最终回复 → 清除该 pending 条目。工具执行走 loop 既有 dispatch 而非手搓，保证 tool_context/连接器一致。
- 触发处（normalizer 文本命令 / slack 按钮 handler）已持有 reply_func / client，恢复输出有处可去。

**D5 resolve 解耦内存 Event，改为状态驱动。**
`gate.resolve` 写 approvals 表状态 + 返回授权校验结果（保留 Change1 的身份校验），不再 `event.set()` 唤醒阻塞协程（已无协程在等）。恢复由触发处在 resolve 成功后显式调用 D4。重启后内存无 Event，但 approvals 表 + session meta 足以恢复——授权决策人集合在重启后需可重建（从 approval_routing + session 重解析，或随 pending 一并持久化）。

**D6 待办式并发：pending 期间新消息照常 run。**
history 已合法 → 新消息正常开 turn。为让 LLM 知晓挂起项，run 时若 session meta 有 pending_approvals，注入一条轻量 context（"你有待审批项 X 未决"）。新 turn 不得擅自重发同一 tool_call（占位结果已表明 awaiting）。

**D7 过期清扫回填。**
`cleanup_stale_approvals`（启动时 + 周期）把超时 pending：approvals 标 timeout + session meta 对应条目移除 + （可选）给会话追加"审批超时未执行"context。审批窗口因无悬挂协程可放宽（如天级）。

## Risks / Trade-offs

- [链式工具的连续性损失] 若门控工具是"调用→看结果→再调用"的中间步，placeholder 让 LLM 在等批期间先往下走，批准后结果以 context（非原生 tool 位）回来 → 推理连续性略损。缓解：我们 medium 门控的工具（send_im_message/run_code/invoke_agent）多为终点动作，触发率低；占位文本明确"awaiting"，LLM 知道等后续。
- [浮动待办被遗忘] 待办式下 pending 可能被用户忘批 → D7 过期回填 + （可选）下次 session 活动时复现提醒兜底。
- [恢复并发竞争] 同 session 恢复与新 turn 可能并发 → 复用 session per-id 锁串行化；恢复持锁执行。
- [授权集合重启重建] D5 重启后授权决策人需可重建 → 随 pending 持久化 approver 身份（requester_user_id / 已通知 target），避免重启后任何人可批。
- [既有阻塞测试改写] 大量 permission_gate/loop 测试假设阻塞返回 decision → 按挂起-恢复语义重写。

## Migration Plan

纯增量、无 schema 迁移。阻塞式审批的旧测试改写为：①发起→断言 stop_reason=awaiting_approval + meta pending；②resolve→断言执行/拒绝 + 续跑结果。上线前内测窗口，无生产会话数据需迁移。

## Resolved Decisions (was Open Questions)

- **恢复后续跑的 run 用独立的预算/turn 计数**（新 run，不接续原 run）。挂起期跨越了真实时间，旧计数无意义；恢复是一次新的执行。
- **不做用户可见的 pending 复现提醒**（YAGNI）。审批卡片本就在会话里可见，过期回填（D7）已兜底"忘批"。唯一保留的"知晓"是 D6 给 LLM 的 context 注入——目的是**防止模型重发同一 gated 工具**，属正确性必需，非用户提醒。超时回填时可附一句"X 超时未执行"使会话自解释。
