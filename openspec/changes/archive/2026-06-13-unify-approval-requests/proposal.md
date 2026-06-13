# unify-approval-requests

## Why

实体关系审计（2026-06-13）发现两套"agent 主动外呼审批人"的审批貌合神离：审批**生命周期状态**在 `approvals`（工具门）和 `reflection_proposals`（反思提案）两张表各建模一遍——`status` / 审批人 / 决定时间 / `risk` / 请求者 / `created_at` / 过期 共约 7 列重复，两套状态机、两套过期机制（工具门 `reconcile_expired` vs 提案 `expires_at` 列）。而且反思那侧的"审批人 IM 回复 → resolve"线**根本没接**：`governance/reflection_gate.py`（resolve + 按类型分派 apply）在 `src/` 里零调用、只有测试调它——审批人收到 DM，回复却无处落，闭环断开。

两者其实是**同一形状**：建审批请求 → `resolve_approvers` + outbound DM 找审批人（已共享）→ 审批人 IM 回复 → 按类型分派 resolve。唯一分叉在"批准后干什么"（工具门恢复挂起的 run / 提案 approve+apply）。这正是这条审计线一路在消灭的"重复状态 + 断链"模式，且审批是人在环的安全核心，值得收成单一真相源。

## What Changes

- **新建 `approval_requests` 表**（`agent_state.db` 嵌入式 Y）作审批生命周期**唯一真相源**：`id · subject_type(tool_call|memory_proposal|skill_proposal) · subject_id · requester_user_id · risk · status(pending→approved/rejected/expired) · approver_user_id · decided_at · reason · routing_key · created_at · expires_at`。工具门与反思提案都汇入它（多态主体 `subject_type`+`subject_id`，约定引用无 FK）
- **`approvals` 表退役** → 被 `approval_requests` 取代：存量行迁为 `subject_type=tool_call`（`tool_name`→`routing_key`、`resolved_at`→`decided_at`）；工具门的恢复上下文（`tool_args` 等）已在 session meta 的 `pending_approvals`（loop.py:1927），新表不冗余，故工具门**无需单独 subject 表**
- **`reflection_proposals` 瘦身**：删 `status` / `reviewer_user_id` / `reviewed_at` / `rejection_reason` / `expires_at`（生命周期搬进 approval_requests），保留 `domain` / `kind` / `target_ref` / `payload_json` / `evidence_json` / `report_id` / `applied_at` / `actor_user_id` / `subject_user_id` / `created_at` / `updated_at`（提案实体 + apply 产出）
- **`approval_allowlist` 改名 `tool_auto_approvals`**：它是工具调用专属的指纹去重自动批（`fingerprint=hash(requester, tool_name, tool_args)`，只对**重复出现的相同工具调用**有意义；提案是一次性唯一实体，不适用）。**不进统一表、保持独立**，只改名 + 体现工具作用域（`governance/approval_allowlist_store.py` 及引用同步）
- **统一审批路由**：新建 router，notify（已共享）→ IM 回复 → 按 `subject_type` 分派：`tool_call`→恢复挂起 run（permission_gate 逻辑）、`memory_proposal`/`skill_proposal`→approve+apply（reflection_gate 逻辑）。替掉现在 `permission_gate.resolve` 与 `reflection_gate.resolve` 两个平行 resolve，并把反思缺的 IM 回复线自然补上（reflection_gate 从零调用变成被统一路由调用）
- 落地**一步到位**（用户选定）：嵌入式 Y 新版本（append 在当前 v33 之后、不硬编码）一次完成建表 + 迁移 + 瘦身 + 改名 + drop approvals

## Capabilities

### New Capabilities

- `approval-request-lifecycle`: 统一审批生命周期——`approval_requests` 单一真相源、`subject_type` 多态主体、统一 router 按类型分派 resolve、统一 pending/expiry 语义；工具门与反思提案共用

### Modified Capabilities

- `approval-suspend-resume`: 挂起-恢复的审批状态行从 `approvals` 表改读 `approval_requests`（恢复上下文仍在 session meta；过期 reconcile 同理）
- `permission-gate`: 审批请求/结果从 `approvals` 表改记 `approval_requests`；resolve 经统一 router 分派（tool_call 分支）
- `standalone-agent-approval`: `/approvals` 端点与审批人列（`approver_user_id`）落在 `approval_requests`（语义不变，表名变更）
- `reflection`: 提案审批生命周期（status/reviewer/applied 审计）经 `approval_requests`；`reflection_proposals` 仅留实体 + apply 产出列；reflection 审批闭环（IM 回复 → 统一 router → approve+apply）接通

> 不改 spec 的关联项：`approval-minimization` 用"allow-list/allow-always"概念描述行为，不提表名，`approval_allowlist`→`tool_auto_approvals` 改名是实现细节、行为不变，故无 delta；`agent-owned-approval` 无 canonical spec（仅归档 change）。

## Impact

- **owning package**：`governance`（approval_requests store + 统一 router + tool_auto_approvals 改名）、`runtime`（agent_state_migrations、loop suspend-resume 接线）、`reflection`（proposal 瘦身 + 接入统一 router）
- **public API surface**：新增 approval_requests store + 统一 router API；`reflection_gate` / `permission_gate` 的两个平行 `resolve` 收敛为一个 router；`reflection_proposals` 读写去生命周期列；`approval_allowlist_store` → 改名模块
- **owned tables**（`agent_state.db`，嵌入式 Y 新版本）：新增 `approval_requests`；drop `approvals`（数据先迁）；`reflection_proposals` 删 5 列；`approval_allowlist` → rename `tool_auto_approvals`
- **config namespace**：无新增（approval routing 配置 `agent.yaml approval` 块不变）
- **cross-module dependencies**：全 agent 侧；agent 零 platform import 维持；`resolve_approvers` + outbound 为已有共享路径
- **migration / shim plan**：嵌入式 Y forward-only 一版完成；带升级路径测试（存量 approvals 行迁移后工具门恢复仍工作、旧 approval_allowlist 行保留）；**最大风险 = 工具门挂起-恢复是 live + 安全敏感**，回归防线见 design/tasks
- **相邻切片**：已确认 5 个在跑 change（conversation-address / delivery-receipts / kb-standalone / trace-tool-spans / unified-file-exchange）均不碰审批/反思
