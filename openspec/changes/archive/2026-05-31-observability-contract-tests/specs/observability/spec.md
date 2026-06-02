## ADDED Requirements

### Requirement: Observability contract test coverage
系统 SHALL 通过自动化 contract tests 验证 agent run 的核心 observability 事件链路。

#### Scenario: Contract tests live in integration layer
- **WHEN** 新增 observability contract tests
- **THEN** 测试文件位于 `tests/integration/`
- **AND** 不向平铺 `tests/` 根目录新增 contract test

#### Scenario: Non-streaming run trace contract is tested
- **WHEN** `agent_loop.run()` 完成且注入了 long-term context sources
- **THEN** 测试覆盖 `injected_context` 与 `agent_run_completed` 两类事件
- **AND** 测试断言两类事件共享同一个 run_id

#### Scenario: Streaming run trace contract is tested
- **WHEN** `agent_loop.run_stream()` 完成且注入了 long-term context sources
- **THEN** 测试覆盖 `injected_context` 与 `agent_run_completed` 两类事件
- **AND** 测试断言两类事件共享同一个 run_id

### Requirement: Observability payload safety tests
系统 SHALL 通过自动化测试验证 trace payload 的安全边界。

#### Scenario: Source attribution raw content is excluded
- **WHEN** source metadata 包含 `content`、`text` 或 `transcript`
- **THEN** 测试断言落库 payload 不包含这些完整原文

#### Scenario: Sensitive payload is redacted
- **WHEN** trace payload 包含 token、password、secret、邮箱或手机号
- **THEN** 测试断言落库 payload 中敏感值被脱敏

#### Scenario: Large payload is truncated
- **WHEN** trace payload 包含超过阈值的大字段
- **THEN** 测试断言落库 payload 被截断并带截断标记

### Requirement: Usage summary ignores non-completion events
系统 SHALL 通过自动化测试验证 usage summary 只统计 completed run events。

#### Scenario: Injected context does not affect usage
- **WHEN** 同一个 run 同时存在 `injected_context` 和 `agent_run_completed`
- **THEN** 测试断言 usage summary 只按 `agent_run_completed` 统计 run_count 和 token totals
