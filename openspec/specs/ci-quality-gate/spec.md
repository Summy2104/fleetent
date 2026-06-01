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
- **THEN** deterministic memory、knowledge-base 和 long-term context evaluation 可以被手动执行
- **AND** 真实模型或真实 provider evaluation 只有在显式设置对应 `FLEETENT_EVAL_*` 环境变量时运行

### Requirement: Agent guidance matches test layers
项目级 agent 指南 SHALL 说明测试目录分层，保证 AI agent 和团队成员按同一规范写测试。

#### Scenario: Root compatibility guidance is removed
- **WHEN** 读者查看 `AGENTS.md` 或 `CLAUDE.md`
- **THEN** 文档不再描述 `tests/` 根目录作为新增或保留测试位置
- **AND** 文档说明历史测试已经迁移到分层目录

