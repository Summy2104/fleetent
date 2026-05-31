## Why

当前测试基本平铺在 `tests/` 根目录下，单元测试、集成测试、端到端 smoke 和未来 evaluation tests
混在一起。随着 observability contract tests、memory / reflection / knowledge-base 质量评估增加，
继续平铺会带来两个问题：

- TDD fail-fast 变慢，开发时不容易只运行快速单元测试。
- CI 无法按测试成本分层执行，慢测试或真实依赖测试容易影响 PR 门禁效率。

本 change 先建立测试目录和命令规范，并同步 `AGENTS.md` / `CLAUDE.md`，让团队和 AI agent 后续写测试时遵循同一规则。

## What Changes

- 定义四类测试目录：
  - `tests/unit/`：单模块、mock 外部依赖、最快。
  - `tests/integration/`：多模块协作、SQLite/Alembic/FastAPI/observability contract。
  - `tests/e2e/`：启动服务或走 CLI/HTTP/IM 的端到端链路。
  - `tests/evaluation/`：memory/reflection/long-term-ctx/knowledge-base 的效果评估。
- 更新 pytest 配置，显式收集分层目录。
- 更新 Makefile，提供分层测试命令。
- 更新 Bitbucket CI，把 PR 门禁拆为 unit 与 integration。
- 更新 `AGENTS.md` 和 `CLAUDE.md` 的测试规范。
- 只迁移少量代表性测试：
  - `tests/smoke/smoke.py` -> `tests/e2e/test_smoke.py`
  - migration / trace / usage / observability contract 类测试放入 `tests/integration/`
  - 保留大规模迁移为后续机械整理，避免本 change 产生无意义大 diff。

## Capabilities

### Modified Capabilities

- `ci-quality-gate`：新增测试分层与 CI 执行策略。

## Impact

- **代码**：不修改运行时代码。
- **测试**：新增测试目录结构，少量迁移代表性测试。
- **CI**：PR 先运行 unit，再运行 integration；e2e/evaluation 不进入默认 PR 门禁。
- **文档**：更新 agent 指南和团队测试规范。
- **不包含**：
  - 不一次性搬迁所有 tests。
  - 不引入真实 LLM / embedding evaluation。
  - 不实现 observability contract tests 的具体测试内容。
  - 不调整业务模块目录。
