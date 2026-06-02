# ci-quality-gate Specification

## Purpose
Define the repository CI gate that verifies pull requests and main branch updates with Bitbucket
Pipelines before code is accepted.
## Requirements
### Requirement: Pull requests run the full test suite

The project SHALL run Bitbucket Pipelines for pull requests and fail the build when the Python test
suite fails.

#### Scenario: Pull request executes unit tests

- **WHEN** a pull request is opened or updated
- **THEN** Bitbucket Pipelines sets test-only environment needed for settings initialization
- **AND** installs project dependencies from the checked-in lockfile
- **AND** initializes the SQLite schema with Alembic
- **AND** runs `uv run pytest`
- **AND** reports a failed build if any test fails

### Requirement: Main branch updates are verified

The project SHALL run the same unit test verification for commits that reach the `main` branch.

#### Scenario: Main branch executes unit tests

- **WHEN** a commit is merged into `main`
- **THEN** Bitbucket Pipelines sets test-only environment needed for settings initialization
- **AND** installs project dependencies from the checked-in lockfile
- **AND** initializes the SQLite schema with Alembic
- **AND** runs `uv run pytest`
- **AND** reports a failed build if any test fails

### Requirement: Layered test suite organization
系统 SHALL 按测试成本和依赖范围组织测试目录。

#### Scenario: Root test files are migrated
- **WHEN** 历史测试迁移完成
- **THEN** `tests/` 根目录不再包含 `test_*.py` 文件
- **AND** 历史测试按 unit、integration、e2e 或 evaluation 放入对应目录

#### Scenario: Test directories remain authoritative
- **WHEN** 团队新增或移动测试
- **THEN** 测试 SHALL 放入 `tests/unit/`、`tests/integration/`、`tests/e2e/` 或 `tests/evaluation/`
- **AND** 不得继续向 `tests/` 根目录新增测试文件

### Requirement: Fast default feedback
PR 门禁 SHALL 优先运行快速且稳定的测试层，避免 e2e 或 evaluation 影响日常开发反馈。

#### Scenario: PR gate excludes evaluation tests
- **WHEN** Bitbucket PR pipeline 运行
- **THEN** pipeline 不默认运行 `tests/evaluation`
- **AND** 不调用真实 LLM 或真实 embedding evaluation

#### Scenario: Evaluation remains manually runnable
- **WHEN** 开发者运行 `uv run pytest tests/evaluation`
- **THEN** deterministic memory、knowledge-base、long-term context、reflection report 和 combined memory/KB embedding evaluation 可以被手动执行
- **AND** 真实模型或真实 provider evaluation 只有在显式设置对应 `FLEETENT_EVAL_*` 环境变量时运行

### Requirement: Agent guidance matches test layers
项目级 agent 指南 SHALL 说明测试目录分层，保证 AI agent 和团队成员按同一规范写测试。

#### Scenario: Root compatibility guidance is removed
- **WHEN** 读者查看 `AGENTS.md` 或 `CLAUDE.md`
- **THEN** 文档不再描述 `tests/` 根目录作为新增或保留测试位置
- **AND** 文档说明历史测试已经迁移到分层目录

### Requirement: Intelligence unit test hardening
常乐负责模块 SHALL 在 MVP foundation 完成后补齐适合单元测试的纯逻辑和边界逻辑覆盖。

#### Scenario: Scoped unit coverage reaches hardening target
- **WHEN** `intelligence-unit-test-hardening` 完成
- **THEN** scoped unit coverage for `fleetent.intelligence`、`fleetent.observability`、`fleetent.config` 和 `scripts.upgrade` 至少达到 75%
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

