# fleetent

面向企业 on-premises 部署的 Lean Agent 平台。Python + FastAPI，无 AI 框架依赖，支持 Slack / Telegram / WhatsApp，数据不出内网。

## 不可逾越的规则

### Commit 规范

格式：`type(scope): 简短描述`，英文、动词开头，scope 可选。

type 只能是：`feat` / `fix` / `refactor` / `test` / `docs` / `chore`。

禁止使用 `update`、`fix bug`、`wip` 等模糊描述；一次 commit 不要混入多个不相关改动。

### TDD Hard Gate

每个实现 task 必须严格按顺序执行：

1. 写测试，运行 `uv run pytest -x -q`，必须看到红。
2. 写实现，运行 `uv run pytest -x -q`，必须看到绿。
3. 可选 refactor，确保测试仍然绿。

如果测试直接绿，说明测试没有覆盖目标行为，需要先修测试。

### OpenSpec 工作流

本项目有 `openspec/` 目录，默认使用 OpenSpec 流：

1. `opsx:propose`：定义 proposal、specs、design（可选）、tasks；`tasks.md` 必须体现 TDD 顺序。
2. 建 worktree + 功能分支。
3. `opsx:apply`：按 task 执行，每个 task 强制 TDD。
4. `opsx:archive`：所有 checkbox 为 `[x]` 后，在当前功能分支归档并同步 specs。
5. 推送分支并清理 worktree；后续在主仓库基于已推送分支决定 merge / PR。

`tasks.md` 中所有实现任务必须拆成 TDD 红绿步骤：先 `Write failing tests` 并运行
`uv run pytest -x -q` 确认红，再实现并运行同一命令确认绿；测试任务必须在对应实现任务之前。
如果 proposal / tasks 没有体现红绿循环，不能进入 implementation。

归档先于合并决策：`opsx:archive` 在功能分支上执行，spec 同步随同一分支进入后续 PR，便于一并
review；archive 表示"实现完成"，不代表已上线到 `main`。

worktree 清理必须满足三个条件：对应分支已推送到 remote（或已建 PR）、worktree 干净、没有未提交
的用户改动。分支尚未推送或存在未提交改动时不得清理，避免丢失工作。

OpenSpec proposal / design 进入 implementation 前必须声明模块边界影响：

- owning package（例如 `runtime` / `platform` / `intelligence` / `observability`）。
- public API surface（允许其他模块 import / 调用的函数、dataclass、service interface）。
- owned tables（新增或修改的持久化表；无则写无）。
- config namespace（新增配置所属命名空间；无则写无）。
- cross-module dependencies（依赖哪些模块 public API，是否触碰共享契约）。
- migration / shim plan（移动平铺模块时如何保留 re-export 兼容和迁移 import）。

## Project Structure & Module Organization

核心代码在 `src/fleetent/`。当前仍有 legacy 平铺模块，新增代码优先按模块化单体 package 组织：
`runtime/`、`governance/`、`platform/`、`channels/`、`intelligence/`、`integrations/`、
`observability/`、`infrastructure/`。平铺模块在被大幅触碰时迁移，旧 import 路径可暂时保留
re-export shim，但 shim 不承载业务逻辑。

关键 legacy 模块包括：`agent_loop.py`（tool-use 循环）、`model_router.py`（模型路由）、
`tool_registry.py` / `tools.py`（工具注册与内置工具）、`server.py`（FastAPI）、`admin.py`（管理 CLI）、
`im_gateway/`（Slack / Telegram 适配器）。

测试按层放在 `tests/unit/`、`tests/integration/`、`tests/e2e/`、`tests/evaluation/`，命名为 `test_<module>.py`。配置样例在 `config/`，Alembic 迁移在 `migrations/`，技能在 `skills/`，文档在 `docs/`。`data/` 是本地运行数据，测试不得直接触碰。

## Build, Test, and Development Commands

- `uv sync`：安装依赖。
- `uv run pytest`：运行完整测试。
- `uv run pytest -x -q`：fail-fast 测试，TDD 循环使用。
- `uv run pytest tests/unit` / `make test-unit`：运行快速单元测试。
- `uv run pytest tests/integration` / `make test-integration`：运行集成测试。
- `uv run pytest tests/e2e` / `make test-e2e`：运行端到端测试；真实服务 smoke 需显式开启。
- `uv run pytest tests/evaluation` / `make test-evaluation`：运行效果评估测试。
- `uv run python scripts/check_test_layers.py` / `make test-layers`：检查 unit / integration 测试层边界。
- `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`：检查已迁移 package 是否跨模块 import internal 实现。
- `uv run ruff format src tests`：格式化。
- `uv run ruff check src tests`：lint。
- `uv run mypy src`：严格类型检查。
- `uv run fleetent "hello"`：运行 CLI agent。
- `uv run fleetent-admin create-user --name "Alice"`：创建用户/API key。
- `uv run uvicorn fleetent.server:app --reload`：启动 HTTP 服务。

## Coding Style & Architecture Rules

- 行长 100，ruff 强制；mypy strict。
- 公开函数必须有完整类型注解；公开 API 使用 Google 风格 docstring。
- 注释只解释“为什么”，不复述“做什么”。
- 新模块结构：import → 可注入常量/配置 → dataclass → 函数。
- 禁止引入 LangChain / LlamaIndex / LangGraph。
- 禁止 ORM；数据库策略是 SQLite-first，不是 SQLite-only。
- 新增或改造数据库代码必须经过统一 DB runtime / store 边界；不得继续扩散 `sqlite3.connect`、`DB_PATH` re-export、SQLite 专属方言到业务层。
- store 层 SQL 使用 named parameters（如 `:user_id`），不要新增 `?` 占位符风格。
- schema lifecycle 由 Alembic 管理；不要在新 store 中复制 `_init_db()` 建表/补列模式。
- 已迁移 package 的 internal 实现不得被其他 package import；跨模块调用必须走 public API。
- 禁止不可注入的全局可变状态；legacy 路径常量在迁移前必须方便 `monkeypatch` 隔离。
- 禁止云托管专有服务破坏数据主权；基础设施组件必须可 self-host。

## Testing Guidelines

pytest 配置为 `asyncio_mode = auto`，async 测试无需 `@pytest.mark.asyncio`。

测试按成本和依赖范围分层：

- `tests/unit/`：单模块行为，mock LLM、数据库、HTTP、sandbox 等外部依赖，作为新增单元测试默认位置。
  unit 不得使用 FastAPI `TestClient` / app lifespan，不得运行 Alembic migration，不得导入
  `tests.integration.*` helper，也不得验证真实 SQLite schema lifecycle / DB runtime orchestration。
  unit 不得导入 `sqlite3`、monkeypatch `DB_PATH` 后创建真实 DB file、调用生产 `_init_db()`，也不得用
  `DATABASE_URL=sqlite:///...` 或 `create_database("sqlite:///...")` 验证 store/runtime 持久化。
  `tmp_path` 只可用于纯解析、配置路径、序列化和可注入文件边界；一旦用于真实 DB file、schema、CRUD 或 store/runtime 协作，
  测试必须放在 integration。只读 legacy shim / public API / path constant 兼容断言可留在 unit。
- `tests/integration/`：多模块协作、SQLite/Alembic/FastAPI、observability trace / usage / logging 等需要真实本地组件的测试。
  FastAPI `TestClient`、Alembic migration、migrated SQLite tables、store/runtime wiring 都属于 integration。
- `tests/e2e/`：启动服务或走 CLI/HTTP/IM 完整链路的端到端测试；默认不进入 PR 门禁，真实服务 smoke 需显式开启。
- `tests/evaluation/`：memory、reflection、long-term context、knowledge-base 等效果评估；不得接入真实 LLM / embedding 服务作为默认测试。
历史平铺测试已迁移到分层目录；不得继续向 `tests/` 根目录新增 `test_*.py`。

TDD 红绿循环优先运行最近相关分层命令，例如 `uv run pytest tests/unit -x -q` 或
`uv run pytest tests/integration -x -q`；收尾必须运行 `uv run pytest -x -q`。
涉及测试归位、测试层规则或新增 unit 测试时，收尾同时运行 `uv run python scripts/check_test_layers.py`。

测试必须隔离外部依赖：LLM 调用 patch `get_client_and_config`，数据库测试放在 integration 并用 `tmp_path` 或统一 DB fixture 隔离，MCP / sandbox / 外部 HTTP 用 `respx` 或 `unittest.mock`。每个测试函数只测一个行为；`permission_gate` 测试使用短超时：`PermissionGate(medium_timeout=0.1)`。

## Gotchas

- `tools.py` 通过 import 副作用注册工具，`agent_loop.py` 顶部必须 import。
- `skill_registry.scan()` 在服务启动时运行，CLI `run()` 每次调用时扫描。
- `context_mgr._keep_tail()` 使用 identity check，不要替换为 `==`。
- Bearer token 格式：`Authorization: Bearer ma-<64hex>`。
- MCP 工具名格式：`{server_id}__{tool_name}`。
- `session_mgr` 原子写：`.json.tmp → rename`；测试中 monkeypatch `session_mgr.SESSIONS_DIR`。

## Security & Configuration

不要提交真实配置或 secret。复制 `config/*.example.*` 后本地修改；API key、Slack/Telegram token、`.env` 都必须留在本机。
