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

#### Scenario: Test directories exist
- **WHEN** 本 change 完成
- **THEN** 仓库包含 `tests/unit/`、`tests/integration/`、`tests/e2e/` 和 `tests/evaluation/`

#### Scenario: New tests have a target layer
- **WHEN** 团队新增测试
- **THEN** 测试应按单元、集成、端到端或效果评估放入对应目录，而不是继续平铺到 `tests/` 根目录

### Requirement: Fast default feedback
PR 门禁 SHALL 优先运行快速且稳定的测试层，避免 e2e 或 evaluation 影响日常开发反馈。

#### Scenario: PR runs unit and integration
- **WHEN** Bitbucket PR pipeline 运行
- **THEN** pipeline 运行 unit tests 和 integration tests
- **AND** 不默认运行 e2e 或 evaluation tests

#### Scenario: Full test command remains available
- **WHEN** 调用 `uv run pytest`
- **THEN** pytest 仍可收集完整测试套件

### Requirement: Agent guidance matches test layers
项目级 agent 指南 SHALL 说明测试目录分层，保证 AI agent 和团队成员按同一规范写测试。

#### Scenario: AGENTS guidance is updated
- **WHEN** 读者查看 `AGENTS.md`
- **THEN** 文档说明 unit、integration、e2e 和 evaluation 测试的目录与适用场景

#### Scenario: CLAUDE guidance is updated
- **WHEN** 读者查看 `CLAUDE.md`
- **THEN** 文档说明 unit、integration、e2e 和 evaluation 测试的目录与适用场景

