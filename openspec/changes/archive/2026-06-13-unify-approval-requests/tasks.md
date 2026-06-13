# unify-approval-requests Tasks

> 每个实现 task 严格 TDD：先写测试见红，再实现见绿。测试任务在对应实现任务之前。
> 本 change 最大风险 = 工具门挂起-恢复是 live + 安全敏感：迁移/收敛每步都要对照 main 基线确认无新增失败。

## 1. schema 迁移（嵌入式 Y 单版本，append after v33）

- [x] 1.1 [测试] integration：最新 Y 版本下 `agent_state.db` 含 `approval_requests`（列齐：subject_type/subject_id/requester_user_id/risk/status/approver_user_id/decided_at/reason/routing_key/created_at/expires_at）、不含 `approvals` 表、含 `tool_auto_approvals` 不含 `approval_allowlist`、`reflection_proposals` 不含 status/reviewer_user_id/reviewed_at/rejection_reason/expires_at（先红）
- [x] 1.2 [测试] integration：升级路径——含存量 `approvals` 行 + `reflection_proposals`（带生命周期列值）+ `approval_allowlist` 行的旧库 migrate-on-open 后：approvals 行迁入 approval_requests（subject_type=tool_call、tool_name→routing_key、resolved_at→decided_at、status/risk 保留）；proposal 的 status/reviewer 等迁入 approval_requests（subject_type 按 domain）；allowlist 行在 tool_auto_approvals 保留（先红）
- [x] 1.3 [实现] `runtime/agent_state_migrations.py` append 新版本（勿硬编码、append after 当前最大）：按 design D2 顺序 建 approval_requests → 迁 approvals → 迁/删 reflection_proposals 生命周期列 → rename approval_allowlist→tool_auto_approvals → drop approvals → 1.1/1.2 转绿

## 2. approval_requests store + tool_auto_approvals 改名

- [x] 2.1 [测试] integration：approval_requests store CRUD——建 pending、置 approved/rejected/expired、按 subject_type 列 pending（统一收件箱）、读单条（先红）
- [x] 2.2 [实现] 新建 `governance` 侧 approval_requests store（named params、经 db.py、agent_scope 注入）→ 2.1 转绿
- [x] 2.3 [测试] unit：守护——全仓无 `approval_allowlist` 标识符（表名/模块/函数）；`tool_auto_approvals` fingerprint 机制行为不变（命中放行、不同参数不命中）（先红）
- [x] 2.4 [实现] `approval_allowlist_store.py` → `tool_auto_approvals` 改名（模块/表/函数/引用同步），逻辑不变 → 2.3 转绿

## 3. 统一审批 router（收敛两个 resolve）

- [x] 3.1 [测试] integration：router 按 subject_type 分派——tool_call→恢复挂起 run；memory_proposal/skill_proposal→approve+apply；reject→置 rejected 不执行后续；三类的 IM 回复入口都路由到它（先红）
- [x] 3.2 [测试] unit：守护——`permission_gate._default_gate.resolve` 与 `reflection_gate.resolve` 两个旧 resolve 入口无残留外部调用（仅 router 内部调其动作函数）（先红）
- [x] 3.3 [实现] 新建统一 router；把 IM 边缘各入口（slack 按钮 / normalizer / tui / server / agent_app / standalone /approvals / reflection 提案 IM 回复）切到 router；旧两 resolve 入口收敛（保留恢复/apply 动作函数）→ 3.1/3.2 转绿
- [x] 3.4 [实现] reflection 审批闭环接通：`_notify_pending_proposal` 建 approval_requests(pending) + 通知；审批人 IM 回复经 router → approve+apply（reflection_gate 现有 apply 动作复用）；全仓确认 reflection_gate 不再是零调用

## 4. 工具门接线迁移 + 回归防线

- [x] 4.1 [测试] integration：工具门全链路对照 main 基线无新增失败——slack approval_approve/reject/always 三按钮、session meta pending_approvals 恢复、reconcile 过期置 expired + 清 meta、standalone GET/POST /approvals、streaming-approval-gating、restart-after-pending 恢复（先红/确认）
- [x] 4.2 [实现] permission_gate / loop 的审批读写从 `approvals` 表切到 approval_requests（恢复上下文仍 session meta）；reconcile 例程改 approval_requests；tool_auto_approvals 短路建 approved → 4.1 转绿

## 5. reflection_proposals 瘦身代码侧

- [x] 5.1 [测试] integration：proposal list/get/序列化从 approval_requests 取状态（status/approver/decided/expires），实体列仍在 reflection_proposals；report_id provenance 不受影响（先红）
- [x] 5.2 [实现] reflection store/序列化去被删 5 列的读写，状态改从 approval_requests join/查；全仓 grep 被删列读写点清零 → 5.1 转绿

## 6. 文档

- [x] 6.1 `docs/architecture/data-model.md` §3.3：重画——approval_requests 入图（多态 subject_type→tool_call(session meta)/proposal）、approvals 退场、reflection_proposals 瘦身去生命周期列、approval_allowlist→tool_auto_approvals 改名仍挂工具门；表计数更新；note 增"审批生命周期单一真相源 + 统一 router 按 subject_type 分派 + 两家族(动作门/变更提案)"；§3.1 宏观图同步
- [x] 6.2 `docs/capabilities/governance.md` + `reflection.md`：审批流描述同步（统一 approval_requests + router；reflection 审批闭环接通；allowlist 改名）
- [x] 6.3 `docs/records/decision-logs/`：追记设计决策与往返理由（两套审批统一、多态主体、tool_auto_approvals 改名 + 两家族分析、为何 report/proposal 不合、为何 allowlist 工具专属、reflection 触发模型本期不动）

## 7. 收尾

- [x] 7.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（审批是安全核心，**特别确认工具门链路零回归**）
- [x] 7.2 全仓 grep 清零：`approval_allowlist`、对退役 `approvals` 表的读写、reflection_proposals 被删 5 列的读写、两旧 resolve 入口的外部调用（迁移历史 / openspec 归档除外）
- [x] 7.3 `openspec validate unify-approval-requests` 通过；所有 checkbox 标记 `[x]`
