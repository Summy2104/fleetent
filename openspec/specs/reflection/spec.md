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
reflection SHALL 可以读取 memory-layer 信号用于分析，但本阶段不得自动修改 memory。

#### Scenario: Memory signal can be used
- **WHEN** memory-layer 返回与 trace 相关的 memory 信号
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
- **THEN** runner 使用 fixture memory_signals patch `memory_layer.search()`

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
reflection SHALL apply approved User Memory proposals through memory-layer public API instead of direct SQL.

#### Scenario: Apply does not write memory table directly
- **WHEN** approved proposal 被应用
- **THEN** reflection 调用 memory-layer public API 修改 User Memory
- **AND** reflection 不直接写 `memory_items` 表
