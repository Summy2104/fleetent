# unify-approval-requests（2026-06-13）

## 背景

- 工具门审批（`approvals`）与 reflection proposal 审批（`reflection_proposals` 上的 5 个生命周期列）长期分裂。
- IM 决策入口也分成 `permission_gate.resolve` 与 `reflection_gate.resolve` 两套路由，反思提案的 IM 回复闭环断开。
- `approval_allowlist` 名称过窄但实际只服务工具门，和 proposal 审批没有关系。

## 决策

- **D1 单一真相源**：新增 `approval_requests` 统一承载审批生命周期，`subject_type=tool_call|memory_proposal|skill_proposal`。
- **D2 subject 多态**：
  - `tool_call` 的 subject 不是独立表，而是 session meta `pending_approvals` 中的挂起上下文；`approval_requests.subject_id` 记 `session_id`。
  - `memory_proposal` / `skill_proposal` 的 subject 是同 id 的 `reflection_proposals` 行。
- **D3 一次性迁移到位**：嵌入式 Y 新版本按顺序执行 `create approval_requests -> migrate approvals -> migrate/drop reflection_proposals lifecycle cols -> rename approval_allowlist -> drop approvals`，forward-only，不保留双写阶段。
- **D4 统一 resolve router**：所有 IM / HTTP / TUI / Slack 按钮入口统一走 `approval_router.resolve_approval_request(...)`，再按 `subject_type` 分派到工具恢复或 proposal apply。
- **D5 `tool_auto_approvals` 只改名不改义**：原 `approval_allowlist` 仍然只服务工具门，fingerprint 机制和 auto-approve 行为不变；不扩展到 reflection proposal。
- **D6 本期不改 reflection 触发模型**：提案仍由 admin / cron 侧触发；本 change 只负责“提案已存在后”的审批闭环。

## 取舍

- 不把 tool-call subject 再建一张表：审批恢复真正需要的上下文本来就在 session meta，复制一份只会制造双真相源。
- 不把 proposal 审批继续留在 `reflection_proposals`：状态、审批人、过期时间和 reason 属于跨域共享生命周期，应从实体表剥离。
- 不把 `tool_auto_approvals` 泛化成通用 proposal allowlist：工具门的 fingerprint 是“同人 + 同工具 + 同参数”的重复放行优化，和 proposal 审批语义不同，强行统一只会引入错配。

## 结果

- agent 侧现在有一条统一审批链：`approval_requests` + `approval_router`。
- tool gate 挂起-恢复链路保持原有 session meta 语义；reflection proposal 的 IM 回复闭环恢复可用。
- platform 继续只读投影 agent 侧审批数据，不引入新的 platform 写路径。
