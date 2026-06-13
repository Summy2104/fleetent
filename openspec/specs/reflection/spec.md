# reflection Specification

## Purpose
Generate structured self-improvement reports from observability traces and read-only memory
signals without automatically applying changes to memory, skills, or knowledge-base content.
## Requirements
### Requirement: Reflection report public API
系统 SHALL 提供 `ReflectionReport`、`ReflectionFinding` 和 `run_reflection(scope)` public API，
用于生成结构化自我改进建议报告。

#### Scenario: Public API is importable
- **WHEN** 调用方从 reflection 模块导入 `ReflectionReport`、`ReflectionFinding` 和 `run_reflection`
- **THEN** 导入成功

#### Scenario: Report contains required fields
- **WHEN** `run_reflection()` 返回 report
- **THEN** report 包含 id、scope、time_window、findings 和 created_at

### Requirement: Trace-based analysis input
reflection SHALL 只通过 observability public API 读取 agent run history。

#### Scenario: Reflection queries traces through public API
- **WHEN** `run_reflection()` 执行
- **THEN** 系统调用 `observability.query_trace_events()` 读取指定 scope 和 time window 的 trace events

#### Scenario: Empty traces produce empty report
- **WHEN** 查询范围内没有 trace events
- **THEN** `run_reflection()` 返回 findings 为空的 report
- **AND** 不抛出异常

### Requirement: Memory input is read-only
reflection SHALL 可以读取 `fleetent.intelligence.memory` 信号用于分析，但本阶段不得自动修改 memory。

#### Scenario: Memory signal can be used
- **WHEN** `fleetent.intelligence.memory` 返回与 trace 相关的 memory 信号
- **THEN** reflection 可以将其用于 finding 生成

#### Scenario: Reflection does not write memory
- **WHEN** `run_reflection()` 生成 memory 相关 finding
- **THEN** 系统不创建、更新或删除 `memory_items`

### Requirement: Foundation finding types
reflection SHALL 在第一阶段支持 `memory_candidate`、`memory_conflict` 和 `skill_opportunity`
三类 finding。

#### Scenario: Memory candidate finding
- **WHEN** trace events 中重复出现同一用户事实，且该事实尚未稳定进入 memory
- **THEN** report 包含 `type="memory_candidate"` 的 finding

#### Scenario: Memory conflict finding
- **WHEN** trace events 或 memory 信号中出现相互矛盾的用户事实
- **THEN** report 包含 `type="memory_conflict"` 的 finding

#### Scenario: Skill opportunity finding
- **WHEN** trace events 中反复出现同类任务模式
- **THEN** report 包含 `type="skill_opportunity"` 的 finding

### Requirement: Reflection report persistence
系统 SHALL 可以保存 reflection report，且保存内容不得包含完整 trace transcript。report SHALL 持久化在统一 `reflection_reports` 表，以 `domain`(memory / skill / knowledge_base)区分;KB report 复用 nullable `signal_summary_json` 列。不再为各域单建报告表。

#### Scenario: Migration creates reflection_reports
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 reflection-owned `reflection_reports` 表（含 `domain` 列），且不含独立的 `kb_reflection_reports` 表

#### Scenario: Persisted report omits raw transcript
- **WHEN** report 被保存
- **THEN** 保存的 payload 包含 finding summary、evidence ids 和 metadata
- **AND** 不包含完整用户对话 transcript

### Requirement: No automatic application
reflection foundation SHALL 只生成建议，不自动应用建议。

#### Scenario: Skill opportunity does not write skill files
- **WHEN** report 包含 `skill_opportunity` finding
- **THEN** 系统不创建、更新或删除 `skills/` 文件

#### Scenario: Knowledge-base is not required
- **WHEN** knowledge-base 未实现或未启用
- **THEN** `run_reflection()` 仍可基于 traces 和 memory 返回 report

### Requirement: Reflection report evaluation fixtures
系统 SHALL 提供 deterministic reflection report evaluation fixtures，用于验证 reflection findings
质量和 transcript redaction 行为。

#### Scenario: Fixture schema is explicit
- **WHEN** evaluation runner 加载 fixture
- **THEN** fixture 包含 name、scope、trace_events、memory_signals、expected_findings、
  forbidden_findings 和 forbidden_persisted_text

#### Scenario: Invalid fixture is rejected
- **WHEN** fixture 缺失必需字段或 finding assertion 格式非法
- **THEN** evaluation runner 报告 fixture validation failure

### Requirement: Deterministic reflection report evaluation
系统 SHALL 默认使用 fake observability traces 和 fake memory signals 运行 reflection report evaluation，
保证评估稳定且不依赖真实外部服务。

#### Scenario: Runner injects fake trace events
- **WHEN** evaluation case 运行
- **THEN** runner 使用 fixture trace_events patch `observability.query_trace_events()`

#### Scenario: Runner injects fake memory signals
- **WHEN** evaluation case 运行
- **THEN** runner 使用 fixture memory_signals patch `fleetent.intelligence.memory.search()`

#### Scenario: Expected findings are validated
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 expected_findings 出现在 `ReflectionReport.findings`

#### Scenario: Forbidden findings are rejected
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 forbidden_findings 不出现在 `ReflectionReport.findings`

#### Scenario: Persisted report redacts raw transcript
- **WHEN** evaluation case 运行完成并保存 reflection report
- **THEN** persisted findings payload 不包含 forbidden_persisted_text snippets

#### Scenario: Evaluation is isolated from production data
- **WHEN** 默认 evaluation case 运行
- **THEN** runner 不调用真实 LLM、embedding provider、KB connector 或 SaaS
- **AND** runner 使用 tmp SQLite，不触碰 `data/`

### Requirement: Optional real-route reflection smoke
系统 SHALL 提供显式启用的真实 route reflection smoke 入口，且默认跳过。

#### Scenario: Real route smoke is skipped by default
- **WHEN** 未设置 `FLEETENT_EVAL_REAL_REFLECTION=1`
- **THEN** real route smoke case 被 skip

#### Scenario: Real route smoke requires explicit local fixture or config
- **WHEN** 设置 `FLEETENT_EVAL_REAL_REFLECTION=1` 但缺少 explicit local fixture 或 config
- **THEN** real route smoke case 被 skip

#### Scenario: Real route smoke is manually runnable
- **WHEN** 设置 `FLEETENT_EVAL_REAL_REFLECTION=1` 且 explicit local fixture/config 完整
- **THEN** runner 可以使用真实 route 运行 smoke fixture

### Requirement: User Memory maintenance proposal lifecycle
reflection SHALL provide a proposal lifecycle for User Memory maintenance actions without directly mutating memory by default.

#### Scenario: Proposal is created as pending
- **WHEN** reflection 发现 User Memory maintenance candidate
- **THEN** 系统创建 status=`pending` 的 proposal
- **AND** 不创建、更新或删除 `memory_items`

#### Scenario: Proposal can be approved
- **WHEN** proposal owner 确认 pending proposal
- **THEN** proposal status 变为 `approved`

#### Scenario: Proposal can be rejected
- **WHEN** proposal owner 拒绝 pending proposal
- **THEN** proposal status 变为 `rejected`

#### Scenario: Applied proposal is recorded
- **WHEN** approved proposal 成功应用到 User Memory
- **THEN** proposal status 变为 `applied`

#### Scenario: Expired proposal cannot be applied
- **WHEN** proposal status 为 `expired`
- **THEN** 系统拒绝应用该 proposal

### Requirement: User Memory owner approval
User Memory maintenance proposal SHALL be owned by the target `user_id`, and memory-changing actions require owner approval unless an explicit low-risk auto-maintenance policy allows the action.

#### Scenario: Proposal has user owner
- **WHEN** reflection 创建 User Memory maintenance proposal
- **THEN** proposal 包含目标 `user_id`
- **AND** 该 `user_id` 是默认确认主体

#### Scenario: Unapproved proposal does not mutate memory
- **WHEN** proposal status 为 `pending`
- **AND** 不存在适用的低风险自动维护策略
- **THEN** apply 操作不修改 User Memory

#### Scenario: Admin is not default owner
- **WHEN** proposal 目标是 User Memory
- **THEN** 系统不允许管理员或 operator 默认替用户确认内容修改

#### Scenario: High-risk action requires owner approval
- **WHEN** proposal action 是 high-risk
- **THEN** 系统必须要求 owner approval
- **AND** 低风险自动维护策略不能执行该 action

### Requirement: Memory maintenance action risk boundaries
reflection SHALL classify User Memory maintenance proposals by risk before apply.

#### Scenario: Merge rewrite and compact require approval by default
- **WHEN** proposal action 是 `merge`、`rewrite` 或 `compact`
- **THEN** proposal 默认为需要 owner approval

#### Scenario: Delete always requires owner approval
- **WHEN** proposal action 是 `delete`
- **THEN** proposal 被标记为 high-risk
- **AND** 系统没有 owner approval 不得执行删除

#### Scenario: Low-risk auto policy is narrow
- **WHEN** 用户显式开启低风险自动维护策略
- **THEN** 系统只允许 low-risk proposal 自动 apply
- **AND** 不允许自动执行 delete、跨用户动作或低置信度冲突处理

### Requirement: Interaction-time confirmation metadata
reflection SHALL mark proposals that are safe to present as lightweight confirmation during a related user interaction.

#### Scenario: Current conversation creates lightweight confirmation candidate
- **WHEN** 当前对话明确修正了用户身份、偏好或当前状态
- **THEN** reflection 可以生成适合交互中轻量确认的 proposal metadata
- **AND** 该 proposal 在用户确认前不修改 User Memory

#### Scenario: Bulk review remains available
- **WHEN** 用户主动请求整理记忆
- **THEN** 系统可以按 user_id 查询 pending maintenance proposals

### Requirement: Shared Memory and KB migration suggestions
reflection SHALL NOT write team、tenant、project or customer shared context into User Memory.

#### Scenario: Shared context candidate is not written to User Memory
- **WHEN** reflection 发现候选内容更像团队共识、项目惯例、客户背景或组织运行经验
- **THEN** 系统创建 `suggest_shared_memory_or_kb` proposal
- **AND** 不创建、更新或删除 User Memory

#### Scenario: Shared Memory is not implemented by this change
- **WHEN** `suggest_shared_memory_or_kb` proposal 被创建
- **THEN** 系统不创建 Shared Memory item
- **AND** 系统不把 team 或 tenant 内容写入 `memory_items.user_id`

### Requirement: Maintenance apply uses Memory public API
reflection SHALL apply approved User Memory proposals through `fleetent.intelligence.memory` public API instead of direct SQL.

#### Scenario: Apply does not write memory table directly
- **WHEN** approved proposal 被应用
- **THEN** reflection 调用 `fleetent.intelligence.memory` public API 修改 User Memory
- **AND** reflection 不直接写 `memory_items` 表

### Requirement: Knowledge-base reflection report public API
reflection SHALL 提供只读 Knowledge Base 质量报告 API，用于发现 KB 缺口和检索质量问题。

#### Scenario: KB reflection API is importable
- **WHEN** 调用方从 `fleetent.intelligence.reflection` 导入 `KnowledgeBaseReflectionReport`、`KnowledgeBaseReflectionFinding` 和 `run_kb_reflection_report`
- **THEN** 导入成功

#### Scenario: KB reflection report contains required fields
- **WHEN** `run_kb_reflection_report()` 返回 report
- **THEN** report 包含 id、scope、time_window、findings、created_at 和 signal_summary

### Requirement: Knowledge-base reflection is read-only
KB reflection SHALL 只生成报告和 findings，不自动修改 Knowledge Base。

#### Scenario: Report does not mutate KB
- **WHEN** KB reflection 发现 missing 或 stale finding
- **THEN** 系统不创建、更新、删除或归档 KB document
- **AND** 不触发 connector sync

#### Scenario: Report does not create KB proposal
- **WHEN** KB reflection 生成 finding
- **THEN** 系统不创建 KB mutation proposal

### Requirement: Knowledge-base reflection inputs use public APIs
KB reflection SHALL 只通过 observability 和 knowledge-base public API 读取信号。

#### Scenario: Observability signal uses public API
- **WHEN** KB reflection 读取 trace、source attribution 或 retrieval event
- **THEN** 系统调用 observability public API

#### Scenario: Knowledge-base signal uses public API
- **WHEN** KB reflection 读取 connector status、search 或 graph signal
- **THEN** 系统调用 knowledge-base public API
- **AND** 不直接查询 knowledge-base owned tables

### Requirement: Knowledge-base reflection finding types
KB reflection SHALL 支持固定 finding 类型，并为每条 finding 保存 evidence 和 recommendation。

#### Scenario: Missing knowledge finding
- **WHEN** 同类 query 多次出现 zero-result、低 source attribution 或低置信检索
- **THEN** report 包含 `type="missing_knowledge"` finding

#### Scenario: Stale document finding
- **WHEN** trace 或 connector metadata 显示文档可能过期
- **THEN** report 包含 `type="stale_document"` finding

#### Scenario: Low retrieval quality finding
- **WHEN** 同一 topic 多次出现低分结果、用户纠正或 source attribution 缺失
- **THEN** report 包含 `type="low_retrieval_quality"` finding

#### Scenario: Connector sync issue finding
- **WHEN** connector latest status 显示 failed、stale 或连续失败
- **THEN** report 包含 `type="connector_sync_issue"` finding

#### Scenario: Entity graph gap finding
- **WHEN** 关系型 query 缺少 graph evidence 或 entity/graph 覆盖不足
- **THEN** report 包含 `type="entity_graph_gap"` finding

#### Scenario: Finding includes evidence
- **WHEN** KB reflection 返回 finding
- **THEN** finding 包含 severity、affected_resource、evidence_refs 和 recommendation

### Requirement: Knowledge-base reflection persistence
系统 SHALL 持久化 KB reflection reports，且不得保存完整用户 transcript 或完整文档正文。KB report SHALL 写入统一 `reflection_reports` 表（`domain=knowledge_base`），不再使用独立 `kb_reflection_reports` 表。KB reflection 仍为**只读**(不在 agent 侧 mutate KB、不创建 agent 侧 KB proposal);KB 的 remediation 由 platform / 摄取面承担。

#### Scenario: KB 报告写入统一表
- **WHEN** 数据库 migration 运行到最新版本，且 KB reflection report 被保存
- **THEN** report 落在 `reflection_reports`（`domain=knowledge_base`），数据库不含 `kb_reflection_reports` 表

#### Scenario: Persisted payload is redacted
- **WHEN** KB reflection report 被保存
- **THEN** payload 只包含 finding summary、evidence ids、短摘要和 metadata
- **AND** 不包含完整用户对话 transcript 或完整文档正文

### Requirement: Knowledge-base reflection evaluation
系统 SHALL 提供 deterministic evaluation，验证 KB reflection findings 和 payload redaction。

#### Scenario: Expected KB findings are validated
- **WHEN** evaluation fixture 运行
- **THEN** expected findings 出现在 report 中

#### Scenario: Forbidden KB findings are rejected
- **WHEN** evaluation fixture 运行
- **THEN** forbidden findings 不出现在 report 中

#### Scenario: KB unavailable does not fail report
- **WHEN** knowledge-base public API 不可用或未启用
- **THEN** report 返回 insufficient signal finding 或 signal summary
- **AND** 不抛出运行时异常

### Requirement: Skill reflection proposal public API
reflection SHALL 提供 Skill proposal lifecycle，用于把 skill opportunity 转成受控待审建议。

#### Scenario: Skill proposal API is importable
- **WHEN** 调用方从 `fleetent.intelligence.reflection` 导入 `SkillProposal`、`generate_skill_proposals`、`approve_skill_proposal`、`reject_skill_proposal` 和 `apply_skill_proposal`
- **THEN** 导入成功

#### Scenario: Skill proposals are persisted
- **WHEN** per-agent `agent_state.db` 的嵌入式迁移运行到最新版本
- **THEN** Skill proposal 持久化在统一的 `reflection_proposals` 表（`domain='skill'`），不存在独立的 `skill_proposals` 表
- **AND** 管理库中不存在 `skill_proposals` 表

### Requirement: Skill proposal types
系统 SHALL 支持 create、update 和 deprecate 三类 Skill proposal。

#### Scenario: Create skill proposal
- **WHEN** traces 或 reflection finding 显示重复任务模式且现有 skill 未覆盖
- **THEN** 系统可以生成 `type="create_skill"` proposal

#### Scenario: Update skill proposal
- **WHEN** 现有 skill 经常触发但失败、缺少约束或步骤过期
- **THEN** 系统可以生成 `type="update_skill"` proposal

#### Scenario: Deprecate skill proposal
- **WHEN** 现有 skill 长期未触发、重复或持续造成低质量结果
- **THEN** 系统可以生成 `type="deprecate_skill"` proposal

#### Scenario: Single ordinary task is ignored
- **WHEN** trace 只包含一次普通任务且没有稳定重复模式
- **THEN** 系统不生成 Skill proposal

### Requirement: Skill proposal evidence and draft
每个 Skill proposal SHALL 包含可审查的 reason、evidence 和建议内容。

#### Scenario: Proposal includes evidence
- **WHEN** proposal 被创建
- **THEN** proposal 包含 reason、evidence_refs、risk_level 和 created_at

#### Scenario: Create proposal includes draft
- **WHEN** proposal type 为 `create_skill`
- **THEN** proposal 包含 suggested_draft 或等价 skeleton

#### Scenario: Update proposal includes diff
- **WHEN** proposal type 为 `update_skill`
- **THEN** proposal 包含 suggested_diff 或 suggested replacement summary

#### Scenario: Persisted proposal is redacted
- **WHEN** proposal 被保存
- **THEN** payload 不包含完整用户 transcript

### Requirement: Skill proposal review lifecycle
Skill proposal SHALL 默认 pending，只有 approved proposal 可以 apply。

#### Scenario: New proposal is pending
- **WHEN** proposal 被创建
- **THEN** status 为 `pending`

#### Scenario: Pending proposal can be approved
- **WHEN** reviewer approve pending proposal
- **THEN** status 变为 `approved`
- **AND** 系统记录 reviewer 和 reviewed_at

#### Scenario: Pending proposal can be rejected
- **WHEN** reviewer reject pending proposal
- **THEN** status 变为 `rejected`
- **AND** 系统记录 reviewer、reviewed_at 和 rejection reason

#### Scenario: Rejected proposal cannot apply
- **WHEN** 调用 apply rejected proposal
- **THEN** 系统 fail fast
- **AND** 不修改 skill

### Requirement: Skill proposal apply boundary
Skill proposal apply SHALL 通过 skill public boundary 执行，不得绕过边界任意写文件。

#### Scenario: Approved proposal can apply
- **WHEN** approved proposal 被 apply
- **THEN** 系统调用 skill public API 或 skill management boundary
- **AND** apply 成功后 status 变为 `applied`

#### Scenario: Apply does not write arbitrary files
- **WHEN** apply proposal
- **THEN** 系统不得根据 LLM 输出直接写任意路径
- **AND** skill name、path 和 content 必须经过 validation

#### Scenario: Missing skill boundary fails fast
- **WHEN** skill public apply boundary 不可用
- **THEN** apply 明确失败或返回 unsupported
- **AND** 不直接修改 `skills/`

### Requirement: Skill proposal generation avoids real LLM by default
系统 SHALL 默认使用 deterministic generator 生成 proposal draft / diff skeleton。

#### Scenario: Real LLM draft generation is skipped by default
- **WHEN** 未设置真实 LLM opt-in 环境变量
- **THEN** 系统不调用真实 LLM 生成 skill draft

#### Scenario: Deterministic generator is testable
- **WHEN** 默认测试运行
- **THEN** proposal draft / diff 输出稳定

### Requirement: Skill proposal evaluation
系统 SHALL 提供 deterministic evaluation，验证 proposal 生成质量和误报控制。

#### Scenario: Expected proposals are validated
- **WHEN** evaluation fixture 包含重复任务、失败 skill 或未使用 skill signal
- **THEN** expected create/update/deprecate proposal 出现

#### Scenario: Forbidden proposals are rejected
- **WHEN** evaluation fixture 只包含普通单次任务
- **THEN** 不生成 forbidden proposal

### Requirement: Reflection trend summary design
reflection SHALL provide an on-demand trend summary over existing reflection reports and proposal lifecycle records.

#### Scenario: Trend summary API is importable
- **WHEN** callers import `ReflectionTrendQuery`, `ReflectionTrendBucket`, `ReflectionTrendSummary`, and `get_reflection_trend_summary`
- **THEN** the imports succeed

#### Scenario: Trend summary reads reflection-owned sources
- **WHEN** a trend summary is generated
- **THEN** it reads only reflection-owned reports and proposal lifecycle tables
- **AND** it does not read raw transcripts or module-internal memory / KB / skill stores

#### Scenario: Findings are bucketed
- **WHEN** reports exist across multiple UTC buckets
- **THEN** the summary returns per-bucket finding counts by finding type

#### Scenario: Proposal lifecycle is aggregated
- **WHEN** memory maintenance and skill proposals exist
- **THEN** the summary returns per-bucket counts by proposal status, risk, and type/action

#### Scenario: Skill proposal trends are global-only
- **WHEN** a trend summary runs with scope other than `global` or `*`
- **THEN** skill proposal counts are not included
- **AND** `global` or `*` scope can aggregate skill proposal counts

#### Scenario: Trend summary is non-mutating
- **WHEN** trend summary runs
- **THEN** it does not create proposals
- **AND** it does not write Memory, Knowledge Base, or Skill content

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

### Requirement: Skill 自进化 apply 写 agent-local bundle
approved 的 skill 提案 apply SHALL 经 agent 侧 `skills` 公共边界把**整个 skill bundle**（`<name>/SKILL.md` + 可带脚本/子目录/文本资源，Agent Skill 标准协议）写进**该 agent 自己的** skills 目录（`<agent home>/skills/<name>/`），并热更新（`registry.reload()`）。写入 SHALL **原子**（先写临时目录 + SKILL.md 注入扫描通过 → 整目录 rename 换入，registry MUST NOT 扫到半成品）。SKILL.md SHALL 带 provenance frontmatter(`source: reflection` / `proposal_id` / `applied_at`)。apply MUST NOT 写其它 agent 的目录、MUST NOT 经 platform（agent-local、自洽）。`update_skill` SHALL 以**全树覆盖**目标 skill;`deprecate_skill` SHALL 以 frontmatter `enabled: false` 软禁用（从 catalog 排除、模型不再发现/自动调用，文件保留可追溯），不物理删。安全由三层保证:审批人 apply 前 review 整个 bundle + SKILL.md 注入扫描 + 脚本执行经 sandbox。

#### Scenario: apply 写整个 bundle 到 agent 自己的 skills 目录
- **WHEN** 一个 approved 的 `create_skill` 提案 apply
- **THEN** 系统把 payload 的整棵文件树（SKILL.md + 脚本等）原子写入 `<agent home>/skills/<name>/` 并 `registry.reload()`，该 skill 立即可用，且不触及其它 agent 的目录

#### Scenario: SKILL.md 注入扫描守门
- **WHEN** 提案的 SKILL.md 命中 severe 注入模式
- **THEN** apply 拒绝写入，提案不进入 applied

#### Scenario: deprecate 软禁用、模型不误用
- **WHEN** 一个 `deprecate_skill` 提案 apply
- **THEN** 该 skill 的 SKILL.md frontmatter 置 `enabled: false`，从 catalog 排除，模型不再发现/自动调用;文件保留

### Requirement: 自进化提案审批走 agent-owned 触达
memory / skill 提案的审批触达 SHALL 复用 **agent-owned** 审批基础设施——经 `agent_config.resolve_approvers`(读 agent.yaml `ApprovalRouting`)解析**配置的审批人**(memory→该记忆 owner;skill→team/tenant 负责人)并经 im_gateway **外呼 DM**(沿用工具门的 `permission_gate._notify_approvers` 路径),审批人经 Slack 按钮 / 文本命令决定。审批人 SHALL **默认为非 requester 的真实负责人/owner**(系统生成的提案无 requester);找不到审批人 SHALL **default-closed**(不自动 apply)。审批触达 MUST 全在 agent 侧,MUST NOT 依赖 platform console。提案审批是 **out-of-band**(无活跃 run),不复用工具门的 run suspend-resume;审批通过后由 apply(按 domain 分派)执行。

#### Scenario: 提案外呼配置审批人、非当前人
- **WHEN** memory 或 skill 提案进入 pending
- **THEN** 系统经 `resolve_approvers` 解析 agent 配置的审批人(memory→owner;skill→team/tenant 负责人)并经 im_gateway DM 之，不路由给该提案的发起者本人

#### Scenario: 无审批人 default-closed
- **WHEN** 配置中解析不到可达审批人
- **THEN** 提案保持 pending、不被自动 apply（default-closed），不回退到 platform console

#### Scenario: 全 agent 侧、不依赖 platform
- **WHEN** standalone agent（无 platform）运行自进化审批
- **THEN** 审批人解析与 DM 触达全在 agent 侧完成，不调用 platform console

