## Why

`clarify-test-layer-boundaries` 先定义了 unit / integration 的可执行边界，并允许短期 legacy
SQLite store 例外。这个例外适合第一轮收敛，但如果长期存在，`tests/unit/` 仍然不能被团队和 AI agent
理解为“单模块、mock 外部依赖、快速反馈”的目录。

当前残留风险主要来自 legacy store 测试：它们通过 `DB_PATH` monkeypatch、`_init_db()`、`sqlite3`
查询、`DATABASE_URL=sqlite:///...` 或 `create_database(sqlite://...)` 验证真实持久化行为。这些测试
本身有价值，但它们验证的是 SQLite schema、store CRUD 或 DB runtime 协作，应归入 integration 层。

本 change 用于清零这些 legacy DB 例外：`tests/unit/` 不再保留真实 SQLite / store persistence 测试。
必要时对混合文件做有限拆分，纯 enum / validation / config 逻辑留在 unit，DB persistence 部分迁到
integration。

## What Changes

- 收紧 test-layer guard：
  - `tests/unit/` 禁止 `sqlite3`。
  - `tests/unit/` 禁止 monkeypatch 或直接引用 production `DB_PATH` 来创建数据库文件。
  - `tests/unit/` 禁止调用 `_init_db()`、`create_database("sqlite:///...")`、设置
    `DATABASE_URL=sqlite:///...` 后验证 store/runtime 持久化。
  - `tests/unit/` 禁止真实 store CRUD / schema 查询类测试。
- 迁移或拆分 legacy DB unit tests：
  - 纯 store persistence 文件整文件迁到 `tests/integration/`。
  - 混合文件有限拆分：纯逻辑测试留 unit，DB-backed tests 移 integration。
  - 已有同名 integration 文件时合并或重命名，避免重复测试语义和 pytest module name 冲突。
- 删除上一轮 guard 中的 legacy DB allowlist；保留的 allowlist 只能用于非 DB 误报，并必须说明原因。
- 更新项目指南，明确 `tmp_path` 不等于 unit：只要用于真实 DB 文件 / migrated schema / store CRUD，
  就属于 integration。

## Out of Scope

- 不修改生产 store API 或 DB runtime。
- 不引入 fake repository / in-memory repository 抽象。
- 不要求把 DB tests 改写成 mock-heavy unit tests。
- 不迁移 e2e / evaluation。
- 不新增真实外部服务调用。
- 不改变 CI 默认是否运行 e2e / evaluation 的策略。

## Module Boundary Impact

- **Owning package**: `ci-quality-gate` / test suite governance。
- **Public API surface**: 无新增生产 public API；收紧既有 `scripts/check_test_layers.py` 的测试层规则。
- **Owned tables**: 无。
- **Config namespace**: 无。
- **Cross-module dependencies**: 无新增 runtime dependency；测试移动时只调整 test imports 和 pytest
  收集路径。
- **Migration / shim plan**: 无数据库迁移；legacy DB 测试迁到 integration 后继续验证同一 schema/store
  行为。

## Impact

- **测试**：`tests/unit/` 不再包含真实 SQLite / DB runtime tests；`tests/integration/` 承担所有
  SQLite schema、store CRUD、migration-backed runtime orchestration。
- **脚本**：test-layer guard 从“迁移高置信 integration tests”升级为“unit 层禁止真实 DB 依赖”。
- **文档**：`AGENTS.md` / `CLAUDE.md` 明确 DB-backed tests 的归属和 `tmp_path` 判断边界。
- **验证**：新增 guard 红绿测试；运行 unit、integration、全量 pytest、ruff、mypy、OpenSpec validate。
