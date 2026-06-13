# reflection Delta

## MODIFIED Requirements

### Requirement: 统一自进化数据模型（report 三域 · proposal 两域）
自进化 SHALL 用**两张表**:统一**观察层** `reflection_reports`（终态只读日志，覆盖三域 memory / skill / knowledge_base——**观察普适**，agent 能读三者就能上报）+ 统一**行动层** `reflection_proposals`（共享审批生命周期，**仅 agent 自有域 memory / skill**）。**KB 不进 `reflection_proposals`**:KB 关系库是 ingest 单写、agent 只读的**租户共享资源**，其 mutation 不属 agent 侧;KB 的 remediation 由 platform / 摄取面承担（读 agent 的 KB report 投影后执行，独立 change）。两表均含 `domain` 列区分域;域特定内容入 JSON 载荷（report 的 `findings_json`、proposal 的 `payload_json`），不为每域单建表。`reflection_proposals` SHALL 提供单一生命周期(status: pending→approved/rejected→applied)与审批审计列（reviewer/applied），memory / skill 共用;apply SHALL 按 `domain` 分派 handler（memory / skill），不复制状态机。

**Provenance**：每条 `reflection_proposals` 行 SHALL 携带 `report_id` 列，关联生成它的源 `reflection_reports` 行（agent 侧库内约定引用，无 DB FK）。`report_id` **可空**——承认 standalone / 历史 / 将来可能的非反思来源（手工）提案没有源报告。`run_reflection` 在一次调用内从同一批 findings 既建 report 又生成 proposal 时，生成的 proposal MUST 写入该 report 的 id;源 report 行 SHOULD 先于引用它的 proposal 行持久化（约定引用、不依赖外键时序）。proposal 的 list / get / 序列化 SHALL 暴露 `report_id`，支持"提案→源报告"与"报告→产出提案"双向追溯。

#### Scenario: 报告统一一张表、三域
- **WHEN** memory / skill / KB reflection 各生成报告
- **THEN** 三者均写入同一 `reflection_reports` 表，以 `domain` 区分，不存在 per-域报告表

#### Scenario: 提案统一一张表、仅 agent 自有两域
- **WHEN** memory 或 skill 生成提案
- **THEN** 写入同一 `reflection_proposals` 表（`domain` ∈ {memory, skill}），经同一套 approve/reject/apply 生命周期处理;域特定数据在 `payload_json`，apply 按 `domain` 分派

#### Scenario: KB 不产 agent 侧提案
- **WHEN** KB reflection 产生 finding
- **THEN** 系统不在 `reflection_proposals` 创建 `domain=knowledge_base` 行，也不在 agent 侧 apply KB mutation;KB finding 仅以 report 形式记录，remediation 留给 platform / 摄取面

#### Scenario: 统一审批收件箱
- **WHEN** 列出待审提案
- **THEN** 一次查询返回跨 memory / skill 的 pending 提案（按 `domain` 可筛），不需 union 多表

#### Scenario: 提案携带源报告 id
- **WHEN** `run_reflection` 从一批 findings 生成 report 并产出 memory / skill 提案
- **THEN** 每条落库的 proposal 的 `report_id` 等于该次 report 的 id;经 list / get 可读出该 `report_id`

#### Scenario: 无源报告的提案 report_id 为空
- **WHEN** 一条 proposal 没有可关联的源报告（历史行 / 非反思来源）
- **THEN** 其 `report_id` 为 NULL，list / get / apply 流程不因此报错（可空语义）
