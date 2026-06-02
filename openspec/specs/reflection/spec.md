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
系统 SHALL 可以保存 reflection report，且保存内容不得包含完整 trace transcript。

#### Scenario: Migration creates reflection_reports
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 reflection-owned `reflection_reports` 表

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
系统 SHALL 持久化 KB reflection reports，且不得保存完整用户 transcript 或完整文档正文。

#### Scenario: Migration creates KB reflection reports
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 reflection-owned `kb_reflection_reports` 表

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
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 reflection-owned `skill_proposals` 表

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

#### Scenario: Trend summary is non-mutating
- **WHEN** trend summary runs
- **THEN** it does not create proposals
- **AND** it does not write Memory, Knowledge Base, or Skill content
