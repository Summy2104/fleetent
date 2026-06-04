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

#### Scenario: Test-only provider key does not clobber real opt-in evaluation
- **WHEN** 默认测试环境需要 `ANTHROPIC_API_KEY=test-key` 初始化 Settings
- **AND** operator 显式设置真实 provider evaluation opt-in
- **THEN** test-only default key handling does not prevent the opt-in real-provider runner from using the operator's configured real credential

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

### Requirement: Unit test layer excludes integration dependencies

`tests/unit/` SHALL contain tests for single-module behavior with external dependencies mocked or
replaced by lightweight fakes. Tests that exercise FastAPI app lifespan, Alembic schema lifecycle,
SQLite-backed store/runtime orchestration, or multi-module runtime wiring SHALL live in
`tests/integration/`.

#### Scenario: FastAPI app lifespan tests are integration tests
- **WHEN** a test uses FastAPI `TestClient`, enters application lifespan, or asserts HTTP endpoint
  behavior through the app object
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: Alembic and migration-backed database tests are integration tests
- **WHEN** a test runs Alembic migrations, imports migration helpers from `tests.integration.*`, or
  validates behavior against migrated SQLite tables
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: Unit tests may use lightweight file fixtures
- **WHEN** a test uses `tmp_path` for pure parsing, configuration path resolution, serialization, or
  an injected file boundary
- **THEN** the test MAY remain under `tests/unit/`
- **AND** it SHALL NOT validate real DB runtime orchestration through that file fixture

#### Scenario: Legacy SQLite store exceptions are explicit
- **WHEN** a legacy SQLite store test cannot be moved in this change without changing production
  boundaries
- **THEN** it MAY remain temporarily in `tests/unit/` only through an explicit test-layer guard
  allowlist entry
- **AND** the allowlist entry SHALL include the reason and the owning cleanup area

### Requirement: Test layer guard prevents new unit/integration drift

The repository SHALL provide a guard command that scans `tests/unit/` for disallowed integration
patterns and fails with actionable diagnostics.

#### Scenario: Guard detects integration-only imports and APIs
- **WHEN** `uv run python scripts/check_test_layers.py` scans `tests/unit/`
- **THEN** it fails if a unit test imports `fastapi.testclient.TestClient`, references `TestClient(`
  for app testing, imports from `tests.integration.*`, calls `apply_migrations`, or runs Alembic
  `command.upgrade`
- **AND** the diagnostic includes file path, line number, and the violated rule

#### Scenario: Guard passes after approved migration
- **WHEN** high-confidence misplaced tests have been moved to `tests/integration/`
- **AND** any temporary legacy exceptions are captured in the guard allowlist
- **THEN** `uv run python scripts/check_test_layers.py` exits successfully

#### Scenario: Project guidance documents the executable boundary
- **WHEN** a developer or AI agent reads project testing guidance
- **THEN** the guidance describes the unit/integration boundary using the same rules enforced by
  `scripts/check_test_layers.py`
- **AND** it tells contributors to run the guard before completing test-suite organization work

### Requirement: Unit test layer has no real database dependencies

`tests/unit/` SHALL NOT contain tests that create, migrate, query, or validate real database
state. SQLite-backed schema lifecycle, store CRUD, and DB runtime orchestration tests SHALL live
under `tests/integration/`.

#### Scenario: SQLite imports are integration-only
- **WHEN** a test imports `sqlite3` or calls `sqlite3.connect`
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: Production DB path mutation is integration-only
- **WHEN** a test monkeypatches or directly mutates production `DB_PATH` to point at a temporary DB
  file
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: Read-only compatibility assertions remain unit-eligible
- **WHEN** a test only asserts legacy re-export shims, public API import surface, or path constant
  values without creating, migrating, querying, or mutating a real database
- **THEN** the test MAY remain under `tests/unit/`
- **AND** the guard SHALL NOT fail it solely because it references a DB-related symbol name

#### Scenario: Store schema initialization is integration-only
- **WHEN** a test calls production `_init_db()` or validates table / column shape for a store
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: SQLite DATABASE_URL runtime is integration-only
- **WHEN** a test sets `DATABASE_URL` to `sqlite:///...` or creates a database runtime with a
  `sqlite:///...` URL to verify persistence behavior
- **THEN** the test belongs under `tests/integration/`
- **AND** it SHALL NOT live under `tests/unit/`

#### Scenario: Pure file fixtures remain allowed in unit tests
- **WHEN** a test uses `tmp_path` for pure file parsing, config path derivation, serialization, or
  an injected non-DB file boundary
- **THEN** the test MAY remain under `tests/unit/`
- **AND** the test SHALL NOT create or query a real database through that fixture

### Requirement: Legacy DB unit exceptions are eliminated

The test-layer guard SHALL no longer allow legacy SQLite / DB-backed tests to remain under
`tests/unit/`.

#### Scenario: Guard fails on DB-backed unit tests
- **WHEN** `uv run python scripts/check_test_layers.py` scans `tests/unit/`
- **THEN** it fails on DB-backed patterns including `sqlite3`, production `DB_PATH` mutation,
  production `_init_db()`, `DATABASE_URL=sqlite:///...`, and `create_database("sqlite:///...")`
- **AND** each diagnostic includes the file path, line number, and violated rule

#### Scenario: Guard has no DB legacy allowlist
- **WHEN** the guard uses an allowlist for temporary false positives
- **THEN** the allowlist SHALL NOT allow real SQLite / DB-backed unit tests
- **AND** any allowlist entry SHALL document a non-DB reason, such as a read-only compatibility
  assertion that does not create or query a database

#### Scenario: Existing DB-backed tests still run as integration tests
- **WHEN** DB-backed tests are migrated out of `tests/unit/`
- **THEN** equivalent tests remain collected under `tests/integration/`
- **AND** they continue to verify the same SQLite schema, store CRUD, or DB runtime behavior

