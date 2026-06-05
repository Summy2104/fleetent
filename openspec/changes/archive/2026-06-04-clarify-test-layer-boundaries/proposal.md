## Why

`tests/` 已经按 unit / integration / e2e / evaluation 分层，但当前 `tests/unit/` 中仍混入了
FastAPI lifespan、Alembic migration、SQLite store / runtime wiring 等非单元测试。典型例子包括
`tests/unit/test_server_lifespan.py` 使用 `TestClient` 触发应用 lifespan，多个 intelligence / memory
测试从 `tests.integration.test_migrations` 导入 `apply_migrations` 并读写真实 SQLite schema。

这会带来两个问题：

- 单元测试目录不再代表“单模块、mock 外部依赖、快速反馈”，TDD 时运行 `tests/unit` 的成本和失败
  来源变得不清楚。
- 新测试没有可执行的防线，后续仍可能把 TestClient / Alembic / 真实 DB runtime 测试继续放进
  `tests/unit/`。

本 change 用于收敛测试层边界：先迁移高置信误放测试，并增加一个轻量检查脚本防回归。目标不是把所有
历史 SQLite legacy store 测试一次性重写为 mock-heavy unit tests，而是让目录语义重新可信。

## What Changes

- 定义 `tests/unit/` 的可执行边界：
  - unit tests 不得使用 FastAPI `TestClient` / app lifespan。
  - unit tests 不得运行 Alembic migration 或从 `tests.integration.*` 导入 migration helper。
  - unit tests 不得验证真实 SQLite schema lifecycle / store runtime orchestration；这些属于
    integration。
  - 允许 `tmp_path` 文件 I/O 用于纯解析、配置路径、序列化和可注入文件边界，但不得因此覆盖真实 DB
    runtime 协作。
- 迁移首批高置信误放测试到 `tests/integration/`，优先覆盖：
  - `test_server_lifespan.py`。
  - 直接使用 `apply_migrations` / `command.upgrade` 的 unit 文件。
  - 已有同名 integration 文件时，合并或重命名避免重复语义。
- 增加测试层 guard 脚本，例如 `scripts/check_test_layers.py`：
  - 扫描 `tests/unit/` 中的禁止模式。
  - 报告具体文件、行号和原因。
  - 支持 allowlist 注释或集中 allowlist，仅用于短期 legacy 例外，并要求写明原因。
- 将 guard 纳入收尾验证和项目指南，避免后续新增测试破坏边界。

## Out of Scope

- 不修改生产行为。
- 不迁移 e2e / evaluation 目录。
- 不一次性重写所有 legacy SQLite store 测试；若确实要保留在 unit，必须通过显式 allowlist 标注为
  legacy 例外。
- 不新增真实 LLM、embedding provider、Google Drive、Confluence 或 IM 外部服务调用。
- 不改变 Bitbucket 默认是否运行 e2e / evaluation 的策略。

## Module Boundary Impact

- **Owning package**: `ci-quality-gate` / test suite governance。
- **Public API surface**: 无新增生产 public API；新增脚本入口 `scripts/check_test_layers.py` 作为开发 /
  CI 辅助命令。
- **Owned tables**: 无。
- **Config namespace**: 无。
- **Cross-module dependencies**: 无新增 runtime dependency；测试迁移仅调整 test package 路径。
- **Migration / shim plan**: 无数据库迁移；测试文件移动时保留 pytest 收集语义，必要时更新 import 路径。

## Impact

- **测试**：`tests/unit/` 中的高置信 integration tests 迁移到 `tests/integration/`；单元测试目录更快、
  失败来源更清楚。
- **脚本**：新增 test-layer guard，防止 `TestClient`、Alembic migration helper、真实 DB runtime
  orchestration 继续进入 unit 层。
- **文档**：更新 `AGENTS.md` / `CLAUDE.md` 的测试分层说明，写清 unit/integration 判定规则和 guard
  命令。
- **验证**：保留 `uv run pytest -x -q` 收尾；新增 guard 验证。
