## ADDED Requirements

### Requirement: Intelligence unit test hardening
常乐负责模块 SHALL 在 MVP foundation 完成后补齐适合单元测试的纯逻辑和边界逻辑覆盖。

#### Scenario: Scoped unit coverage reaches hardening target
- **WHEN** `intelligence-unit-test-hardening` 完成
- **THEN** scoped unit coverage for `fleetent.intelligence`、`fleetent.observability`、`fleetent.memory_layer`、`fleetent.config` 和 `scripts.upgrade` 至少达到 75%
- **AND** 该目标只作为本 change 的完成标准，不自动变成仓库级 CI coverage gate

#### Scenario: Unit tests focus on pure and boundary logic
- **WHEN** 新增相关 unit tests
- **THEN** 测试优先覆盖聚合逻辑、payload / error parsing、risk gate、redaction、TTL / stale 规则、connector fake-client failure branches
- **AND** 测试不得依赖真实 LLM、真实 embedding provider、真实 Google Drive 或真实 Confluence 服务

#### Scenario: Integration tests remain responsible for runtime orchestration
- **WHEN** DB / vector backend / trace SQLite / KB ingest-search 编排行为需要验证
- **THEN** 这些行为继续由 integration tests 覆盖
- **AND** 不要求把现有 integration tests 改写为 mock-heavy unit tests

### Requirement: Intelligence test distribution remains layered
常乐负责模块 SHALL 保持 unit、integration、evaluation 和 e2e/smoke 的职责分离。

#### Scenario: Evaluation tests remain deterministic by default
- **WHEN** 开发者运行 `tests/evaluation`
- **THEN** memory、knowledge-base、long-term context、reflection 和 combined embedding evaluation 默认使用 deterministic fixtures
- **AND** 真实 LLM / embedding provider evaluation 仍然只在显式设置 `FLEETENT_EVAL_*` 环境变量时运行

#### Scenario: External SaaS smoke tests remain opt-in
- **WHEN** 开发者运行默认测试或 PR gate
- **THEN** Google Drive / Confluence 真实 smoke tests 不连接真实 SaaS
- **AND** smoke tests 只有在显式设置对应环境变量和 credential reference 时才执行真实外部调用
