## ADDED Requirements

### Requirement: Long-term context evaluation fixtures
系统 SHALL 提供 deterministic long-term context evaluation fixtures，用于验证 memory / knowledge
context 是否按预期注入 agent prompt。

#### Scenario: Fixture schema is explicit
- **WHEN** evaluation runner 加载 fixture
- **THEN** fixture 包含 name、user_id、agent_id、query、available_tokens、memories、knowledge、
  expected_text、forbidden_text、expected_sources 和 forbidden_sources

#### Scenario: Invalid fixture is rejected
- **WHEN** fixture 缺失必需字段或 source assertion 格式非法
- **THEN** evaluation runner 报告 fixture validation failure

### Requirement: Deterministic long-term context evaluation
系统 SHALL 默认使用 fake memory 和 fake knowledge provider 运行 long-term context evaluation，
保证评估稳定且不依赖真实外部服务。

#### Scenario: Runner injects fake provider results
- **WHEN** evaluation case 运行
- **THEN** runner 使用 fixture 中的 fake memory 和 fake knowledge provider results 调用 `build_context()`

#### Scenario: Expected text is validated
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 expected_text snippets 出现在 `BuiltContext.text`

#### Scenario: Forbidden text is rejected
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 forbidden_text snippets 不出现在 `BuiltContext.text`

#### Scenario: Expected sources are validated
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 expected_sources 出现在 `BuiltContext.sources`

#### Scenario: Forbidden sources are rejected
- **WHEN** evaluation case 运行完成
- **THEN** runner 验证 forbidden_sources 不出现在 `BuiltContext.sources`

#### Scenario: Evaluation is isolated from production data
- **WHEN** 默认 evaluation case 运行
- **THEN** runner 不调用真实 LLM、embedding provider、KB connector 或 SaaS
- **AND** runner 不触碰 `data/`

### Requirement: Optional real-provider long-term context smoke
系统 SHALL 提供显式启用的真实 provider long-term context smoke 入口，且默认跳过。

#### Scenario: Real provider smoke is skipped by default
- **WHEN** 未设置 `FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT=1`
- **THEN** real provider smoke case 被 skip

#### Scenario: Real provider smoke requires explicit configuration
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT=1` 但缺少 provider credentials 或配置
- **THEN** real provider smoke case 被 skip

#### Scenario: Real provider smoke is manually runnable
- **WHEN** 设置 `FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT=1` 且 provider 配置完整
- **THEN** runner 可以使用真实 provider 运行 smoke fixture
