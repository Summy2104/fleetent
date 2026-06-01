## ADDED Requirements

### Requirement: Combined real embedding evaluation guard
系统 SHALL 提供 combined memory + knowledge-base real embedding evaluation 入口，且默认跳过。

#### Scenario: Combined real embedding evaluation is skipped by default
- **WHEN** 未设置 `FLEETENT_EVAL_REAL_EMBEDDING=1`
- **THEN** combined real embedding evaluation case 被 skip

#### Scenario: Combined real embedding evaluation requires provider config
- **WHEN** 设置 `FLEETENT_EVAL_REAL_EMBEDDING=1` 但缺少 endpoint、model、API key 或 dimensions
- **THEN** combined real embedding evaluation case 被 skip

#### Scenario: Combined real embedding evaluation is manually runnable
- **WHEN** 设置 `FLEETENT_EVAL_REAL_EMBEDDING=1` 且 HTTP embedding provider 配置完整
- **THEN** runner 可以使用真实 HTTP embedding provider 运行 memory 和 KB fixture

#### Scenario: Combined evaluation isolates storage
- **WHEN** combined deterministic 或 real embedding evaluation 运行
- **THEN** runner 使用 tmp fleetent SQLite 和 tmp vector SQLite
- **AND** 不触碰 `data/`
