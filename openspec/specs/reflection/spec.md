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
