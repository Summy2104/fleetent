## ADDED Requirements

### Requirement: 统一自进化数据模型（1 report + 1 proposal · 三域）
自进化 SHALL 用**两张表**承载三域(memory / skill / knowledge_base):统一**观察层** `reflection_reports`（终态只读日志）与统一**行动层** `reflection_proposals`（共享审批生命周期）。两表均含 `domain` 列区分域;域特定内容入 JSON 载荷（report 的 `findings_json`、proposal 的 `payload_json`），不为每域单建表。`reflection_proposals` SHALL 提供单一生命周期(status: pending→approved/rejected→applied)与审批审计列（reviewer/applied），三域共用;apply SHALL 按 `domain` 分派到对应 handler（memory / skill / kb），不复制状态机。

#### Scenario: 报告统一一张表、按 domain 区分
- **WHEN** memory / skill / KB reflection 各生成报告
- **THEN** 三者均写入同一 `reflection_reports` 表，以 `domain` 区分，不存在 per-域报告表

#### Scenario: 提案统一一张表、共享生命周期
- **WHEN** 任一域生成提案
- **THEN** 写入同一 `reflection_proposals` 表，经同一套 approve/reject/apply 生命周期处理;域特定数据在 `payload_json`，apply 按 `domain` 分派

#### Scenario: 统一审批收件箱
- **WHEN** 列出待审提案
- **THEN** 一次查询返回跨三域的 pending 提案（按 `domain` 可筛），不需 union 多表

### Requirement: Knowledge-base 自进化提案
KB reflection SHALL 可由 findings 生成 **KB mutation proposals**（`domain=knowledge_base`），经审批后 SHALL 通过 knowledge-base public API 执行;在审批前 SHALL NOT 自动修改 KB。v1 SHALL 支持动作 `archive_stale_doc` 与 `resync_connector`;其余动作（如 reingest / rerun_extraction / flag_gap）SHALL 可后续以新 `kind` + handler 扩展，不改表结构。

#### Scenario: stale 文档生成可审批提案
- **WHEN** KB reflection 产生 `stale_document` finding
- **THEN** 系统可生成 `kind=archive_stale_doc` 的 `reflection_proposals`（domain=knowledge_base），状态 pending，不立即改 KB

#### Scenario: 审批后经 public API 执行
- **WHEN** 管理员 approve 一个 KB 提案并触发 apply
- **THEN** 系统经 knowledge-base public API 执行该动作（如归档文档 / 触发 connector 同步），不直接写 KB owned tables

#### Scenario: 审批前不改 KB
- **WHEN** KB 提案处于 pending / rejected
- **THEN** 系统不创建、更新、删除、归档 KB document，也不触发 connector sync

### Requirement: 自进化提案审批走 agent-owned 触达
三域(memory/skill/kb)提案的审批触达 SHALL 复用 **agent-owned** 审批基础设施——经 `agent_config.resolve_approvers`(读 agent.yaml `ApprovalRouting`)解析**配置的审批人**(team/tenant 负责人)并经 im_gateway **外呼 DM**(沿用工具门的 `permission_gate._notify_approvers` 路径),审批人经 Slack 按钮 / 文本命令决定。审批人 SHALL **默认为非 requester 的真实负责人**(系统生成的提案无 requester);找不到审批人 SHALL **default-closed**(不自动 apply)。审批触达 MUST 全在 agent 侧,MUST NOT 依赖 platform console。提案审批是 **out-of-band**(无活跃 run),不复用工具门的 run suspend-resume;审批通过后由 apply(按 domain 分派)执行。

#### Scenario: 提案外呼配置审批人、非当前人
- **WHEN** 任一域提案进入 pending
- **THEN** 系统经 `resolve_approvers` 解析 agent 配置的审批人(team/tenant 负责人)并经 im_gateway DM 之，不路由给该提案的发起者本人

#### Scenario: 无审批人 default-closed
- **WHEN** 配置中解析不到可达审批人
- **THEN** 提案保持 pending、不被自动 apply（default-closed），不回退到 platform console

#### Scenario: 全 agent 侧、不依赖 platform
- **WHEN** standalone agent（无 platform）运行自进化审批
- **THEN** 审批人解析与 DM 触达全在 agent 侧完成，不调用 platform console

## MODIFIED Requirements

### Requirement: Reflection report persistence
系统 SHALL 可以保存 reflection report，且保存内容不得包含完整 trace transcript。report SHALL 持久化在统一 `reflection_reports` 表，以 `domain`(memory / skill / knowledge_base)区分;KB report 复用 nullable `signal_summary_json` 列。不再为各域单建报告表。

#### Scenario: Migration creates reflection_reports
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 reflection-owned `reflection_reports` 表（含 `domain` 列），且不含独立的 `kb_reflection_reports` 表

#### Scenario: Persisted report omits raw transcript
- **WHEN** report 被保存
- **THEN** 保存的 payload 包含 finding summary、evidence ids 和 metadata
- **AND** 不包含完整用户对话 transcript

### Requirement: Knowledge-base reflection persistence
系统 SHALL 持久化 KB reflection reports，且不得保存完整用户 transcript 或完整文档正文。KB report SHALL 写入统一 `reflection_reports` 表（`domain=knowledge_base`），不再使用独立 `kb_reflection_reports` 表。

#### Scenario: KB 报告写入统一表
- **WHEN** 数据库 migration 运行到最新版本，且 KB reflection report 被保存
- **THEN** report 落在 `reflection_reports`（`domain=knowledge_base`），数据库不含 `kb_reflection_reports` 表

#### Scenario: Persisted payload is redacted
- **WHEN** KB reflection report 被保存
- **THEN** payload 只包含 finding summary、evidence ids、短摘要和 metadata
- **AND** 不包含完整用户对话 transcript 或完整文档正文

## REMOVED Requirements

### Requirement: Knowledge-base reflection is read-only

**Reason**: KB 自进化已纳入统一行动层(`self-evolution-split` 早已规定"KB → platform console 审"，本 change 落实)。KB reflection 不再是纯只读——findings 可生成**经审批**的 KB mutation proposals。

**Migration**: 由新要求「Knowledge-base 自进化提案」取代。约束保留:**审批前不自动改 KB**(pending/rejected 不触动 KB document 或 connector sync);变更只能经审批 + knowledge-base public API 执行。
