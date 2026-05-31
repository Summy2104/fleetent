## ADDED Requirements

### Requirement: Knowledge-base retrieval evaluation fixtures
系统 SHALL 提供 deterministic retrieval evaluation fixtures，用于验证 KB ingest/chunking/search 质量基线。

#### Scenario: Fixture schema is explicit
- **WHEN** evaluation runner 加载 fixture
- **THEN** fixture 包含 name、documents、queries、expected_chunks 和 forbidden_chunks

#### Scenario: Invalid fixture is rejected
- **WHEN** fixture 缺失必需字段
- **THEN** evaluation runner 报告 fixture validation failure

### Requirement: Deterministic retrieval evaluation
系统 SHALL 默认使用 deterministic embedding 和 isolated storage 运行 KB retrieval evaluation。

#### Scenario: Runner ingests documents
- **WHEN** evaluation case 运行
- **THEN** runner 将 fixture documents 导入 tmp knowledge-base store

#### Scenario: Expected chunks are validated
- **WHEN** query 运行完成
- **THEN** runner 验证 expected chunks 或 snippets 出现在 top-k 结果中

#### Scenario: Forbidden chunks are rejected
- **WHEN** query 运行完成
- **THEN** runner 验证 forbidden chunks 或 snippets 不出现在结果中

#### Scenario: Evaluation isolates storage
- **WHEN** evaluation case 运行
- **THEN** SQLite 使用 tmp path
- **AND** 不触碰 `data/`

### Requirement: Optional real embedding retrieval evaluation
系统 SHALL 提供显式启用的真实 embedding retrieval evaluation，默认跳过。

#### Scenario: Real embedding evaluation is skipped by default
- **WHEN** 未设置 `FLEETENT_EVAL_REAL_EMBEDDING=1`
- **THEN** real embedding evaluation case 被 skip

#### Scenario: Real embedding evaluation requires provider credentials
- **WHEN** 设置 `FLEETENT_EVAL_REAL_EMBEDDING=1` 但缺少 provider credentials
- **THEN** real embedding evaluation case 被 skip

#### Scenario: Real embedding evaluation is manually runnable
- **WHEN** 设置 `FLEETENT_EVAL_REAL_EMBEDDING=1` 且 provider 配置完整
- **THEN** runner 可以使用真实 HTTP embedding provider 运行 fixture
