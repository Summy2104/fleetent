## ADDED Requirements

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
