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

1. `opsx:propose`：定义 proposal、specs、design（可选）、tasks。
2. 建 worktree + 功能分支。
3. `opsx:apply`：按 task 执行，每个 task 强制 TDD。
4. merge / PR，清理 worktree。
5. `opsx:archive`：所有 checkbox 为 `[x]` 后归档并同步 specs。

`tasks.md` 中测试任务必须在对应实现任务之前。

## Project Structure & Module Organization

核心代码在 `src/fleetent/`。关键模块包括：`agent_loop.py`（tool-use 循环）、`model_router.py`（模型路由）、`tool_registry.py` / `tools.py`（工具注册与内置工具）、`server.py`（FastAPI）、`admin.py`（管理 CLI）、`im_gateway/`（Slack / Telegram 适配器）。

测试在 `tests/`，命名为 `test_<module>.py`。配置样例在 `config/`，Alembic 迁移在 `migrations/`，技能在 `skills/`，文档在 `docs/`。`data/` 是本地运行数据，测试不得直接触碰。

## Build, Test, and Development Commands

- `uv sync`：安装依赖。
- `uv run pytest`：运行完整测试。
- `uv run pytest -x -q`：fail-fast 测试，TDD 循环使用。
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
- 禁止 ORM；使用 `aiosqlite` 直接写 SQL。
- 禁止不可注入的全局可变状态；路径常量必须方便 `monkeypatch` 隔离。
- 禁止云托管专有服务破坏数据主权；基础设施组件必须可 self-host。

## Testing Guidelines

pytest 配置为 `asyncio_mode = auto`，async 测试无需 `@pytest.mark.asyncio`。

测试必须隔离外部依赖：LLM 调用 patch `get_client_and_config`，SQLite 路径用 `tmp_path + monkeypatch`，MCP / sandbox / 外部 HTTP 用 `respx` 或 `unittest.mock`。每个测试函数只测一个行为；`permission_gate` 测试使用短超时：`PermissionGate(medium_timeout=0.1)`。

## Gotchas

- `tools.py` 通过 import 副作用注册工具，`agent_loop.py` 顶部必须 import。
- `skill_registry.scan()` 在服务启动时运行，CLI `run()` 每次调用时扫描。
- `context_mgr._keep_tail()` 使用 identity check，不要替换为 `==`。
- Bearer token 格式：`Authorization: Bearer ma-<64hex>`。
- MCP 工具名格式：`{server_id}__{tool_name}`。
- `session_mgr` 原子写：`.json.tmp → rename`；测试中 monkeypatch `session_mgr.SESSIONS_DIR`。

## Security & Configuration

不要提交真实配置或 secret。复制 `config/*.example.*` 后本地修改；API key、Slack/Telegram token、`.env` 都必须留在本机。
