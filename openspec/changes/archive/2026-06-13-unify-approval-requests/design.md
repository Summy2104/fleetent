# unify-approval-requests Design

## Context

两套审批的事实（已核实）：
- **工具门**：`approvals` 表（id/session_id/requester_user_id/risk_level/tool_name/tool_args/status/approver_user_id/created_at/resolved_at）+ session meta `pending_approvals`（恢复上下文，loop.py:1927）+ slack 按钮（approval_approve/reject/always）→ `permission_gate._default_gate.resolve` → 恢复挂起 run。**live + 安全敏感**。
- **反思提案**：`reflection_proposals`（实体列 + 生命周期列 status/reviewer_user_id/reviewed_at/rejection_reason/expires_at）；`_notify_pending_proposal` 经 `resolve_approvers`+outbound DM 通知审批人（已接）；但 `governance/reflection_gate.resolve`（approve+apply 分派）**src 零调用、仅测试**——IM 回复线没接，闭环断。
- **共享**：两者都走 `resolve_approvers`（agent.yaml `approval` 块）+ outbound DM 找审批人。
- `approval_allowlist`（fingerprint=hash(requester,tool_name,tool_args) 的 allow-always）是工具门专属。当前 Y 最大版本 v33。

## Goals / Non-Goals

**Goals:**
- 审批生命周期收成单一真相源 `approval_requests`，消除两表 ~7 列重复 + 两套状态机/过期
- 接通反思审批闭环（IM 回复 → 统一 router → approve+apply）
- 两个平行 resolve 收敛为一个按 subject_type 分派的 router
- 工具门行为**零回归**（恢复、过期、按钮、standalone 端点）

**Non-Goals:**
- 不合并 `reflection_reports` 与 `reflection_proposals`（1:N 基数 + KB 仅 report，前序讨论已定）
- 不把 `tool_auto_approvals`（原 allowlist）并入统一表（工具专属指纹去重，提案不适用）
- 不动 approval routing 配置（`agent.yaml approval` 块）、不动 resolve_approvers/outbound
- 不引入跨 run 预算等无关项

## Decisions

**D1：approval_requests 多态主体，subject 数据各归各处**
`subject_type`+`subject_id` 多态引用（约定，无 FK，同 `target_ref` 模式）。tool_call 的 subject 是 session meta 的 pending 项（无独立表）；memory/skill 的 subject 是 `reflection_proposals` 行。生命周期列只在 approval_requests。

**D2：一步到位的嵌入式 Y 新版本（append after v33，不硬编码）**
一版迁移内按序：①建 `approval_requests`；②`INSERT ... SELECT` 把存量 `approvals` 行迁入（subject_type='tool_call'、tool_name→routing_key、resolved_at→decided_at、risk_level→risk）；③`reflection_proposals` 删 5 生命周期列、把其状态迁入 approval_requests（subject_type 按 domain）；④`approval_allowlist` RENAME 到 `tool_auto_approvals`；⑤`DROP TABLE approvals`。forward-only。顺序保证 drop 前数据已迁。

**D3：统一 router 收敛两个 resolve**
新建 router（governance 侧）：入参 approval_id + decision + actor → 读 approval_requests.subject_type → 分派：tool_call 走 permission_gate 的恢复逻辑、memory/skill 走 reflection 的 approve+apply 逻辑。IM 边缘（slack 按钮 / 命令、standalone /approvals、reflection 提案的 IM 回复）统一调它。删 `permission_gate._default_gate.resolve` 与 `reflection_gate.resolve` 两个旧入口（保留各自的恢复/apply *动作* 函数，被 router 调）。守护测试断言两旧 resolve 入口无残留外部调用。

**D4：tool_auto_approvals 仅改名 + 作用域正名**
表/模块/函数名 `approval_allowlist*` → `tool_auto_approvals*`；fingerprint 机制、列、auto-approve 逻辑不变。它在 router 之前短路：命中即把 approval_requests 直接建成 approved（或不建 pending），与现行 allowlist 短路语义一致。

**D5：reflection 触发模型本期不改**
reflection 仍由 admin maintenance CLI 触发（现状）；本 change 只接通"提案已存在后"的审批闭环。"reflection 是否改为 run 内/定时触发"是独立议题，不在本 change（避免一次动太多）。

## Risks / Trade-offs

- [工具门挂起-恢复回归——本 change 最大风险] → 全链路测试对照 main 基线必须无新增失败：slack 三按钮、session meta pending、reconcile 过期、standalone /approvals、streaming-approval-gating、restart-after-pending；迁移带升级路径测试（存量 approvals 行迁移后恢复仍工作）
- [一步到位迁移出错难回滚] → forward-only 但内测窗口可重置；迁移每步幂等/有序；升级路径测试覆盖"含存量 approvals + reflection_proposals + approval_allowlist 行的旧库"全量升级
- [两个 resolve 收敛漏改某调用点] → 全仓 grep 两旧 resolve 入口清零 + 守护测试；IM 边缘各入口（slack/normalizer/tui/server/agent_app）逐一切到 router
- [reflection_proposals 删列牵连序列化/查询] → 全仓 grep 被删 5 列的读写点；list/get 改从 approval_requests join 取状态
- [approval_requests 与 session meta 双写一致性（tool_call）] → 沿用现有"approvals 行 + session meta"双写模式（本就如此，只是表名变），同事务/同锁路径不变

## Migration Plan

嵌入式 Y 单版本完成建表+迁移+瘦身+改名+drop（D2 顺序）。无数据回填缺口（存量行就地迁）。回滚=git revert + 库重置（上线前窗口）。代码与迁移同 change 落地。

## Open Questions

（无——统一层面、多态主体、tool_auto_approvals 改名、一步到位、reflection 触发模型不动，均已与用户对齐。）
