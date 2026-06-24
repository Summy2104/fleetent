# test-infrastructure Specification

## Purpose
TBD - created by archiving change test-infra-migration-speedup. Update Purpose after archive.
## Requirements
### Requirement: Cached migrated-database helper for integration tests

Integration tests that need a migrated SQLite database MUST obtain it through a single
shared helper that constructs the schema once per process and reuses it. The helper
SHALL run the real Alembic `upgrade head` exactly once into a template database, then
materialize each requested database by copying that template. Each test MUST still
receive its own database file so per-test isolation is preserved.

#### Scenario: First call builds the template via real migrations

- **WHEN** the shared `apply_migrations(db_path)` helper is called for the first time in a process
- **THEN** the real Alembic `upgrade head` runs once to produce a template database
- **AND** the requested `db_path` is created with a schema byte-identical to a freshly migrated database

#### Scenario: Subsequent calls copy the cached template

- **WHEN** the shared helper is called again in the same process
- **THEN** it materializes the database by copying the cached template instead of re-running Alembic
- **AND** each caller receives a distinct database file that can be mutated without affecting other tests

#### Scenario: Migration-logic tests are unaffected

- **WHEN** a test exercises migration behavior itself (step-wise upgrade/downgrade to a specific revision)
- **THEN** it continues to invoke Alembic directly rather than the cached helper

### Requirement: Unit tests stay free of database-backed patterns

Tests under `tests/unit` MUST NOT embed a `sqlite:///` `DATABASE_URL`, as enforced by
`scripts/check_test_layers.py`. Tests that only verify configuration or environment
precedence (and never open a database) SHALL express their values with a non-database
scheme so the layer gate passes.

#### Scenario: Layer gate passes on a clean unit suite

- **WHEN** `scripts/check_test_layers.py` scans `tests/unit`
- **THEN** it reports no `sqlite-database-url` violations and exits with status 0

#### Scenario: Precedence-only tests avoid sqlite URLs

- **WHEN** a unit test asserts config/env `DATABASE_URL` precedence without opening a database
- **THEN** it uses a non-sqlite scheme value and its precedence assertions remain valid

### Requirement: 真实入口冒烟,不 mock 掉被测入口

系统 SHALL 有冒烟测试**执行真实入口路径**,使"测试绿"蕴含"入口能启动",而非被 mock/fixture 掩盖。冒烟 SHALL NOT mock 掉被测的入口本身(如 mock `loop.run` 来测一次性、用预先 `set_state_db` 的 fixture 掩盖平台裸启动)。

至少覆盖:
- **平台裸启动**:以 subprocess 真起 `fleetent platform serve`(或等价的 `python -m uvicorn fleetent.server:app`，仅限测试基础设施中直接使用 ASGI app 入口时),轮询 `/health` 返回 200;进程退出/超时即 fail。
- **agent serve**:以 subprocess 真起 `fleetent agent run <id> --port`,`/health`(或 `/chat`)可达。
- **一次性 run()**:`run_sync` 在 `get_client_and_config` 边界打桩 LLM,`_run → run()` 真实执行(见 agent-runtime-cli)。

#### Scenario: 平台裸启动冒烟捕获 boot 崩溃

- **WHEN** 平台裸启动冒烟运行(subprocess uvicorn + /health 轮询)
- **THEN** 平台无法启动(如 lifespan 崩)时冒烟 fail,而非被 TestClient+fixture 掩盖

#### Scenario: 冒烟用 subprocess 而非 TestClient 测裸启动

- **WHEN** 验证平台/agent 的真实启动
- **THEN** 经 subprocess 起真实进程 + HTTP 探活,不靠 TestClient(后者会掩盖裸启动路径的 wiring 缺失)

#### Scenario: 一次性冒烟不 mock run 本身

- **WHEN** 一次性入口冒烟运行
- **THEN** 它只在 LLM 边界(`get_client_and_config`)打桩,真实执行 `run()`;入口与 run 签名不匹配 SHALL 被捕获

