# reflection Delta

## MODIFIED Requirements

### Requirement: 统一自进化数据模型（report 三域 · proposal 两域）
自进化 SHALL 用**两张表**:统一**观察层** `reflection_reports`（终态只读日志，覆盖三域 memory / skill / knowledge_base——**观察普适**，agent 能读三者就能上报）+ 统一**行动层** `reflection_proposals`（提案实体，**仅 agent 自有域 memory / skill**）。**KB 不进 `reflection_proposals`**:KB 关系库是 ingest 单写、agent 只读的**租户共享资源**，其 mutation 不属 agent 侧;KB 的 remediation 由 platform / 摄取面承担（读 agent 的 KB report 投影后执行，独立 change）。两表均含 `domain` 列区分域;域特定内容入 JSON 载荷（report 的 `findings_json`、proposal 的 `payload_json`），不为每域单建表。

**审批生命周期不在 proposal 上**：提案的审批生命周期（pending→approved/rejected、审批人、决定时间、过期）SHALL 落在统一的 `approval_requests` 表（subject_type=`memory_proposal`/`skill_proposal`，见 `approval-request-lifecycle`），`reflection_proposals` 仅保留提案实体与 **apply 产出**列（`domain` / `kind` / `target_ref` / `payload_json` / `evidence_json` / `report_id` / `applied_at` / `actor_user_id` / `subject_user_id` / `created_at` / `updated_at`），MUST NOT 再自带 `status` / `reviewer_user_id` / `reviewed_at` / `rejection_reason` / `expires_at` 等生命周期列。apply SHALL 按 `domain` 分派 handler（memory / skill），不复制状态机。提案的审批闭环（审批人 IM 回复 → 统一 router → approve+apply）经统一审批路由接通。

**Provenance**：每条 `reflection_proposals` 行 SHALL 携带 `report_id` 列，关联生成它的源 `reflection_reports` 行（agent 侧库内约定引用，无 DB FK）。`report_id` **可空**——承认 standalone / 历史 / 将来可能的非反思来源（手工）提案没有源报告。`run_reflection` 在一次调用内从同一批 findings 既建 report 又生成 proposal 时，生成的 proposal MUST 写入该 report 的 id;源 report 行 SHOULD 先于引用它的 proposal 行持久化（约定引用、不依赖外键时序）。proposal 的 list / get / 序列化 SHALL 暴露 `report_id`，支持"提案→源报告"与"报告→产出提案"双向追溯。

#### Scenario: 报告统一一张表、三域
- **WHEN** memory / skill / KB reflection 各生成报告
- **THEN** 三者均写入同一 `reflection_reports` 表，以 `domain` 区分，不存在 per-域报告表

#### Scenario: 提案实体与审批生命周期分离
- **WHEN** memory 或 skill 生成提案
- **THEN** 提案实体写入 `reflection_proposals`（仅实体+apply 产出列），其审批生命周期写入 `approval_requests`（subject_type 对应 memory/skill proposal）；`reflection_proposals` 不含 status/reviewer/expires 列

#### Scenario: KB 不产 agent 侧提案
- **WHEN** KB reflection 产生 finding
- **THEN** 系统不在 `reflection_proposals` 创建 `domain=knowledge_base` 行，也不在 agent 侧 apply KB mutation;KB finding 仅以 report 形式记录，remediation 留给 platform / 摄取面

#### Scenario: 统一审批收件箱
- **WHEN** 列出待审提案
- **THEN** 经 `approval_requests` 一次查询返回跨 memory / skill（及 tool_call）的 pending 项，按 `subject_type` 可筛

#### Scenario: 提案审批闭环接通
- **WHEN** 审批人对一条提案的 DM 回复 approve
- **THEN** 经统一审批 router 分派到 apply，提案被 apply（memory 写记忆 / skill 写 bundle）;此前 reflection 审批回复无处落的断链消除
